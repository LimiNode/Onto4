"""Deterministic candidate assessment delegates to the Onto4 core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from onto4.core import AssessmentContext, AssessmentResult, evaluate

from .candidates import FormalizationCandidate


@dataclass(frozen=True)
class CandidateAssessment:
    candidate: FormalizationCandidate
    context_id: str
    result: AssessmentResult


def assess_candidate(
    candidate: FormalizationCandidate,
    context: AssessmentContext,
) -> CandidateAssessment:
    """Assess one candidate without choosing among competing candidates."""

    return CandidateAssessment(
        candidate=candidate,
        context_id=candidate.context_id,
        result=evaluate(candidate.formalization, context),
    )


def assess_candidates(
    candidates: Iterable[FormalizationCandidate],
    contexts: Mapping[str, AssessmentContext],
) -> tuple[CandidateAssessment, ...]:
    """Assess candidates against their explicitly named contexts."""

    assessments: list[CandidateAssessment] = []
    for candidate in candidates:
        try:
            context = contexts[candidate.context_id]
        except KeyError as exc:
            raise KeyError(
                f"No assessment context named '{candidate.context_id}' for candidate '{candidate.id}'."
            ) from exc
        assessments.append(assess_candidate(candidate, context))
    return tuple(assessments)
