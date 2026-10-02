"""Meta-level aggregation; this module never produces an Onto4 verdict."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections import defaultdict
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
    invalid_reasons: tuple[str, ...] = ()


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
    context_ids = {item.context_id for item in collected}
    formalization_ids = {item.candidate.formalization_id for item in collected}
    varies_by_context = len(context_ids) > 1
    varies_by_formalization = len(formalization_ids) > 1
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
    identity_conflicts = _formalization_identity_conflicts(collected)
    invalid = tuple(dict.fromkeys((*invalid, *identity_conflicts)))
    if invalid:
        return AssessmentLandscape(
            assessments=collected,
            status=CrossCandidateStatus.InvalidRequest,
            unresolved_candidate_ids=unresolved,
            invalid_candidate_ids=invalid,
            varies_by_context=varies_by_context,
            varies_by_formalization=varies_by_formalization,
            invalid_reasons=(
                "formalization_id_conflict",
            ) if identity_conflicts else (),
        )
    if not collected or unresolved:
        return AssessmentLandscape(
            assessments=collected,
            status=CrossCandidateStatus.FormalizationUnresolved,
            unresolved_candidate_ids=unresolved,
            invalid_candidate_ids=invalid,
            varies_by_context=varies_by_context,
            varies_by_formalization=varies_by_formalization,
        )

    verdicts = {item.result.verdict for item in collected}
    if len(verdicts) == 1:
        status = CrossCandidateStatus.StableAcrossCandidates
    else:
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


def _formalization_identity_conflicts(
    assessments: tuple[CandidateAssessment, ...],
) -> tuple[str, ...]:
    """Return candidates that violate the formalization-id precondition.

    A shared ``formalization_id`` is a caller-provided identity claim. Every
    candidate carrying that id must have equal formalization structure and
    assumptions; otherwise aggregation fails closed instead of trusting the id.
    """

    groups: dict[str, list[CandidateAssessment]] = defaultdict(list)
    for item in assessments:
        groups[item.candidate.formalization_id].append(item)

    conflicts: list[str] = []
    for items in groups.values():
        if len(items) < 2:
            continue
        baseline = (items[0].candidate.formalization, items[0].candidate.assumptions)
        if any((item.candidate.formalization, item.candidate.assumptions) != baseline for item in items[1:]):
            conflicts.extend(item.candidate.id for item in items)
    return tuple(dict.fromkeys(conflicts))
