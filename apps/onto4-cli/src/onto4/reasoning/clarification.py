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
                id=f"meaning:{ambiguity.term}",
                kind=ClarificationKind.Meaning,
                text=f"Что именно означает «{ambiguity.term}» в этом вопросе?",
                target_ids=(ambiguity.term,),
            )

        landscape = context.landscape
        if landscape.status is CrossCandidateStatus.FormalizationUnresolved:
            unresolved = tuple(
                item
                for item in context.assessments
                if item.candidate.id in landscape.unresolved_candidate_ids
            )
            kind = ClarificationKind.Reference
            if any(
                diagnostic.code == "unknown_predicate"
                for item in unresolved
                for diagnostic in item.result.diagnostics
            ):
                kind = ClarificationKind.Meaning
            return ClarificationQuestion(
                id=f"unresolved:{','.join(landscape.unresolved_candidate_ids)}",
                kind=kind,
                text="Какой референс или смысл нужно уточнить для формализации?",
                target_ids=landscape.unresolved_candidate_ids,
            )

        if landscape.status is CrossCandidateStatus.ContextDependent:
            contexts = tuple(dict.fromkeys(item.context_id for item in context.assessments))
            return ClarificationQuestion(
                id="context:disambiguate",
                kind=ClarificationKind.Perspective,
                text="Какой контекст должен определять оценку этого утверждения?",
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
            targets = tuple(
                dict.fromkeys(
                    [
                        *(f"formalization:{item.candidate.formalization_id}" for item in context.assessments),
                        *(f"context:{item.context_id}" for item in context.assessments),
                    ]
                )
            )
            return ClarificationQuestion(
                id="mixed:disambiguate",
                kind=ClarificationKind.Meaning,
                text="Нужно отдельно уточнить смысловое чтение и контекст оценки.",
                target_ids=targets,
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
