"""Typed clarification concepts and deterministic fixture policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol

from .assessment import CandidateAssessment
from .candidates import FormalizationCandidate
from .cross_candidate import AssessmentLandscape, CrossCandidateStatus
from .interpretation import InterpretationSpace


class ClarificationKind(str, Enum):
    Meaning = "Meaning"
    Ontology = "Ontology"
    Reference = "Reference"
    Presupposition = "Presupposition"
    Evidence = "Evidence"
    Perspective = "Perspective"
    Context = "Context"
    Formalization = "Formalization"


@dataclass(frozen=True)
class ClarificationQuestion:
    id: str
    kind: ClarificationKind
    text: str
    target_ids: tuple[str, ...]
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClarificationTurn:
    previous_interpretation_id: str
    question_id: str
    answer: str
    successor_interpretation_id: str


@dataclass(frozen=True)
class ClarificationState:
    turns: tuple[ClarificationTurn, ...] = ()

    def record(
        self,
        *,
        previous_interpretation_id: str,
        question_id: str,
        answer: str,
        successor_interpretation_id: str,
    ) -> "ClarificationState":
        if self.turns and previous_interpretation_id != self.turns[-1].successor_interpretation_id:
            raise ValueError(
                "Clarification history is discontinuous: expected previous "
                f"interpretation {self.turns[-1].successor_interpretation_id!r}, "
                f"got {previous_interpretation_id!r}."
            )
        return ClarificationState(
            turns=(
                *self.turns,
                ClarificationTurn(
                    previous_interpretation_id=previous_interpretation_id,
                    question_id=question_id,
                    answer=answer,
                    successor_interpretation_id=successor_interpretation_id,
                ),
            )
        )


@dataclass(frozen=True)
class ClarificationContext:
    interpretation: InterpretationSpace
    candidates: tuple[FormalizationCandidate, ...]
    assessments: tuple[CandidateAssessment, ...]
    landscape: AssessmentLandscape


class ClarificationPolicy(Protocol):
    def choose(self, context: ClarificationContext) -> ClarificationQuestion | None:
        ...


class KindAwareClarificationPolicy(ClarificationPolicy, Protocol):
    """Resolve a requested kind without inventing question provenance."""

    def choose_for_kind(
        self,
        context: ClarificationContext,
        kind: ClarificationKind,
    ) -> ClarificationQuestion | None:
        """Return a justified question of the requested kind, if one exists."""

        ...


@dataclass(frozen=True)
class FixtureClarificationPolicy:
    """Choose a provenance-aware question using deterministic rules."""

    transitions: Mapping[tuple[str, str, str], InterpretationSpace] = field(
        default_factory=dict
    )

    def questions(
        self, context: ClarificationContext
    ) -> tuple[ClarificationQuestion, ...]:
        """List deterministic questions justified by the supplied provenance."""

        interpretation = context.interpretation
        if interpretation.ambiguities:
            ambiguity = interpretation.ambiguities[0]
            return (
                ClarificationQuestion(
                    id=f"meaning:{ambiguity.id}",
                    kind=ClarificationKind.Meaning,
                    text=f"Что именно означает «{ambiguity.term}» в этом вопросе?",
                    target_ids=(ambiguity.id,),
                ),
            )

        landscape = context.landscape
        if landscape.status is CrossCandidateStatus.FormalizationUnresolved:
            unresolved = tuple(
                item
                for item in context.assessments
                if item.candidate.id in landscape.unresolved_candidate_ids
            )
            diagnostic_codes = {
                diagnostic.code
                for item in unresolved
                for diagnostic in item.result.diagnostics
            }
            question_specs = (
                (
                    "unknown_symbol",
                    ClarificationKind.Reference,
                    "Какой объект или референс имеется в виду?",
                ),
                (
                    "unknown_predicate",
                    ClarificationKind.Meaning,
                    "Как следует понимать этот предикат или термин?",
                ),
                (
                    "ontology_unresolved",
                    ClarificationKind.Ontology,
                    "Какие онтологические допущения следует использовать?",
                ),
                (
                    "presupposition_unresolved",
                    ClarificationKind.Presupposition,
                    "Какую предпосылку следует принять или отвергнуть?",
                ),
            )
            questions = tuple(
                ClarificationQuestion(
                    id=(
                        f"unresolved:{kind.value.lower()}:"
                        f"{','.join(landscape.unresolved_candidate_ids)}"
                    ),
                    kind=kind,
                    text=text,
                    target_ids=landscape.unresolved_candidate_ids,
                )
                for code, kind, text in question_specs
                if code in diagnostic_codes
            )
            if questions:
                return questions
            return (
                ClarificationQuestion(
                    id=f"unresolved:{','.join(landscape.unresolved_candidate_ids)}",
                    kind=ClarificationKind.Formalization,
                    text="Что нужно уточнить, чтобы завершить формализацию этого чтения?",
                    target_ids=landscape.unresolved_candidate_ids,
                ),
            )

        if landscape.status is CrossCandidateStatus.ContextDependent:
            contexts = tuple(dict.fromkeys(item.context_id for item in context.assessments))
            return (
                ClarificationQuestion(
                    id="context:disambiguate",
                    kind=ClarificationKind.Context,
                    text="Какой из представленных контекстов следует использовать для оценки?",
                    target_ids=contexts,
                    choices=contexts,
                ),
            )

        if landscape.status is CrossCandidateStatus.FormalizationConflict:
            reading_targets = tuple(
                dict.fromkeys(
                    item.candidate.reading_id
                    for item in context.assessments
                    if item.candidate.reading_id is not None
                )
            )
            has_reading_provenance = bool(context.assessments) and all(
                item.candidate.reading_id is not None
                for item in context.assessments
            )
            if has_reading_provenance:
                return (
                    ClarificationQuestion(
                        id="meaning:formalization",
                        kind=ClarificationKind.Meaning,
                        text="Какое смысловое чтение утверждения вы имеете в виду?",
                        target_ids=reading_targets,
                        choices=reading_targets,
                    ),
                )
            targets = tuple(item.candidate.id for item in context.assessments)
            return (
                ClarificationQuestion(
                    id="formalization:disambiguate",
                    kind=ClarificationKind.Formalization,
                    text="Какой вариант формализации следует рассматривать?",
                    target_ids=targets,
                    choices=targets,
                ),
            )

        if landscape.status is CrossCandidateStatus.MixedDependence:
            reading_targets = tuple(
                dict.fromkeys(
                    item.candidate.reading_id
                    for item in context.assessments
                    if item.candidate.reading_id is not None
                )
            )
            has_reading_provenance = bool(context.assessments) and all(
                item.candidate.reading_id is not None
                for item in context.assessments
            )
            if has_reading_provenance:
                return (
                    ClarificationQuestion(
                        id="mixed:meaning",
                        kind=ClarificationKind.Meaning,
                        text="Какое смысловое чтение утверждения вы имеете в виду?",
                        target_ids=reading_targets,
                        choices=reading_targets,
                    ),
                )
            targets = tuple(dict.fromkeys(item.candidate.id for item in context.assessments))
            return (
                ClarificationQuestion(
                    id="mixed:formalization",
                    kind=ClarificationKind.Formalization,
                    text="Какой вариант формализации следует рассматривать?",
                    target_ids=targets,
                    choices=targets,
                ),
            )

        return ()

    def choose(self, context: ClarificationContext) -> ClarificationQuestion | None:
        questions = self.questions(context)
        return questions[0] if questions else None

    def choose_for_kind(
        self,
        context: ClarificationContext,
        kind: ClarificationKind,
    ) -> ClarificationQuestion | None:
        return next(
            (question for question in self.questions(context) if question.kind is kind),
            None,
        )

    def successor(
        self,
        *,
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
    ) -> tuple[InterpretationSpace, ClarificationTurn]:
        key = (interpretation.id, question.id, answer)
        try:
            successor = self.transitions[key]
        except KeyError as exc:
            raise KeyError(f"No clarification fixture transition for {key!r}.") from exc
        return successor, ClarificationTurn(
            previous_interpretation_id=interpretation.id,
            question_id=question.id,
            answer=answer,
            successor_interpretation_id=successor.id,
        )
