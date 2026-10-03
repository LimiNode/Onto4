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


@dataclass(frozen=True)
class FixtureClarificationPolicy:
    """Choose a provenance-aware question using deterministic rules."""

    transitions: Mapping[tuple[str, str, str], InterpretationSpace] = field(
        default_factory=dict
    )

    def choose(self, context: ClarificationContext) -> ClarificationQuestion | None:
        interpretation = context.interpretation
        if interpretation.ambiguities:
            ambiguity = interpretation.ambiguities[0]
            return ClarificationQuestion(
                id=f"meaning:{ambiguity.id}",
                kind=ClarificationKind.Meaning,
                text=f"Что именно означает «{ambiguity.term}» в этом вопросе?",
                target_ids=(ambiguity.id,),
            )

        landscape = context.landscape
        if landscape.status is CrossCandidateStatus.FormalizationUnresolved:
            unresolved = tuple(
                item
                for item in context.assessments
                if item.candidate.id in landscape.unresolved_candidate_ids
            )
            kind = ClarificationKind.Formalization
            text = "Что нужно уточнить, чтобы завершить формализацию этого чтения?"
            if any(
                diagnostic.code == "unknown_symbol"
                for item in unresolved
                for diagnostic in item.result.diagnostics
            ):
                kind = ClarificationKind.Reference
                text = "Какой объект или референс имеется в виду?"
            elif any(
                diagnostic.code == "unknown_predicate"
                for item in unresolved
                for diagnostic in item.result.diagnostics
            ):
                kind = ClarificationKind.Meaning
                text = "Как следует понимать этот предикат или термин?"
            return ClarificationQuestion(
                id=f"unresolved:{','.join(landscape.unresolved_candidate_ids)}",
                kind=kind,
                text=text,
                target_ids=landscape.unresolved_candidate_ids,
            )

        if landscape.status is CrossCandidateStatus.ContextDependent:
            contexts = tuple(dict.fromkeys(item.context_id for item in context.assessments))
            return ClarificationQuestion(
                id="context:disambiguate",
                kind=ClarificationKind.Context,
                text="Какой из представленных контекстов следует использовать для оценки?",
                target_ids=contexts,
                choices=contexts,
            )

        if landscape.status is CrossCandidateStatus.FormalizationConflict:
            targets = tuple(
                item.candidate.reading_id or item.candidate.id for item in context.assessments
            )
            return ClarificationQuestion(
                id="meaning:formalization",
                kind=ClarificationKind.Meaning,
                text="Какое смысловое чтение утверждения вы имеете в виду?",
                target_ids=targets,
                choices=targets,
            )

        if landscape.status is CrossCandidateStatus.MixedDependence:
            reading_targets = tuple(
                dict.fromkeys(
                    item.candidate.reading_id
                    for item in context.assessments
                    if item.candidate.reading_id is not None
                )
            )
            if len(reading_targets) == len(context.assessments):
                return ClarificationQuestion(
                    id="mixed:meaning",
                    kind=ClarificationKind.Meaning,
                    text="Какое смысловое чтение утверждения вы имеете в виду?",
                    target_ids=reading_targets,
                    choices=reading_targets,
                )
            targets = tuple(dict.fromkeys(item.candidate.id for item in context.assessments))
            return ClarificationQuestion(
                id="mixed:formalization",
                kind=ClarificationKind.Formalization,
                text="Какой вариант формализации следует рассматривать?",
                target_ids=targets,
                choices=targets,
            )

        return None

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
