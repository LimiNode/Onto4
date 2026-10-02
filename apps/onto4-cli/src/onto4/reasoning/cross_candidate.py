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
    MixedDependence = "MixedDependence"
    FormalizationUnresolved = "FormalizationUnresolved"
    InvalidRequest = "InvalidRequest"


@dataclass(frozen=True)
class AssessmentLandscape:
    """The result of comparing candidate assessments at the meta level."""

    assessments: tuple[CandidateAssessment, ...]
    status: CrossCandidateStatus
    unresolved_candidate_ids: tuple[str, ...] = ()
    invalid_candidate_ids: tuple[str, ...] = ()
    varies_by_context: bool = False
    varies_by_formalization: bool = False


def aggregate_assessments(
    assessments: Iterable[CandidateAssessment],
) -> AssessmentLandscape:
    """Classify a landscape without collapsing it to a single Onto4 verdict.

    Invalid requests and unresolved candidates remain distinct at the landscape
    level. For fully assessed candidates, equal verdicts are stable. When
    verdicts differ, the candidate identity axes determine the status: a
    single formalization across contexts is context-dependent, multiple
    formalizations in one context are a formalization conflict, and changing
    both axes is mixed dependence rather than an attribution to context.
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
    if invalid:
        return AssessmentLandscape(
            assessments=collected,
            status=CrossCandidateStatus.InvalidRequest,
            unresolved_candidate_ids=unresolved,
            invalid_candidate_ids=invalid,
        )
    if not collected or unresolved:
        return AssessmentLandscape(
            assessments=collected,
            status=CrossCandidateStatus.FormalizationUnresolved,
            unresolved_candidate_ids=unresolved,
            invalid_candidate_ids=invalid,
        )

    verdicts = {item.result.verdict for item in collected}
    if len(verdicts) == 1:
        status = CrossCandidateStatus.StableAcrossCandidates
        varies_by_context = False
        varies_by_formalization = False
    else:
        varies_by_context = len({item.context_id for item in collected}) > 1
        varies_by_formalization = len({item.candidate.formalization_id for item in collected}) > 1
        if varies_by_context and not varies_by_formalization:
            status = CrossCandidateStatus.ContextDependent
        elif varies_by_formalization and not varies_by_context:
            status = CrossCandidateStatus.FormalizationConflict
        else:
            status = CrossCandidateStatus.MixedDependence
    return AssessmentLandscape(
        assessments=collected,
        status=status,
        varies_by_context=varies_by_context,
        varies_by_formalization=varies_by_formalization,
    )
