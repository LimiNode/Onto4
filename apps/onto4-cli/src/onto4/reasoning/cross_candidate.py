"""Meta-level aggregation; this module never produces an Onto4 verdict."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from onto4.core import AssessmentState

from .assessment import CandidateAssessment


class CrossCandidateStatus(str, Enum):
    StableAcrossCandidates = "StableAcrossCandidates"
    ContextDependent = "ContextDependent"
    FormalizationConflict = "FormalizationConflict"
    FormalizationUnresolved = "FormalizationUnresolved"


@dataclass(frozen=True)
class AssessmentLandscape:
    """The result of comparing candidate assessments at the meta level."""

    assessments: tuple[CandidateAssessment, ...]
    status: CrossCandidateStatus
    unresolved_candidate_ids: tuple[str, ...] = ()
    invalid_candidate_ids: tuple[str, ...] = ()


def aggregate_assessments(
    assessments: Iterable[CandidateAssessment],
) -> AssessmentLandscape:
    """Classify a landscape without collapsing it to a single Onto4 verdict.

    Any unresolved or invalid candidate keeps the landscape formally
    unresolved. For fully assessed candidates, equal verdicts are stable;
    differing verdicts across named contexts are context-dependent; differing
    verdicts within one context are a formalization conflict.
    """

    collected = tuple(assessments)
    unresolved = tuple(
        item.candidate.id
        for item in collected
        if item.result.state is AssessmentState.FormalizationUnresolved
    )
    invalid = tuple(
        item.candidate.id
        for item in collected
        if item.result.state is AssessmentState.InvalidRequest
    )
    if not collected or unresolved or invalid:
        return AssessmentLandscape(
            assessments=collected,
            status=CrossCandidateStatus.FormalizationUnresolved,
            unresolved_candidate_ids=unresolved,
            invalid_candidate_ids=invalid,
        )

    verdicts = {item.result.verdict for item in collected}
    if len(verdicts) == 1:
        status = CrossCandidateStatus.StableAcrossCandidates
    elif len({item.context_id for item in collected}) > 1:
        status = CrossCandidateStatus.ContextDependent
    else:
        status = CrossCandidateStatus.FormalizationConflict
    return AssessmentLandscape(assessments=collected, status=status)
