"""Bridge typed workflow decisions into deterministic clarification policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from onto4.providers import (
    DecisionProfile,
    DeterministicDecisionPolicy,
    TypedDecision,
    TypedDecisionProvider,
    TypedDecisionRequest,
)
from onto4.reasoning import ClarificationContext, PipelineDisposition

from .ask import determine_disposition

CLARIFICATION_REFINEMENT_CHOICES = (
    "NeedMeaningClarification",
    "NeedOntologyClarification",
    "NeedReferenceClarification",
    "NeedContextClarification",
    "NeedPresuppositionClarification",
)
EVIDENCE_REFINEMENT_CHOICES = ("SelectEvidencePath",)
COMPLETE_REFINEMENT_CHOICES = ("PresentResult",)
FAILURE_REFINEMENT_CHOICES = ("ReportFailure",)


@dataclass(frozen=True)
class ClarificationDecisionResult:
    request: TypedDecisionRequest
    decision: TypedDecision
    selected_choice: str | None
    admissible_disposition: PipelineDisposition
    disposition: PipelineDisposition | None


def _refinement_choices(disposition: PipelineDisposition) -> tuple[str, ...]:
    if disposition is PipelineDisposition.AskClarification:
        return CLARIFICATION_REFINEMENT_CHOICES
    if disposition is PipelineDisposition.NeedEvidence:
        return EVIDENCE_REFINEMENT_CHOICES
    if disposition is PipelineDisposition.Complete:
        return COMPLETE_REFINEMENT_CHOICES
    return FAILURE_REFINEMENT_CHOICES


def build_clarification_request(
    context: ClarificationContext,
    profile: DecisionProfile,
) -> TypedDecisionRequest:
    """Encode meta-level clarification state as a bounded typed request."""

    admissible_disposition, _ = determine_disposition(context)
    state: Mapping[str, object] = {
        "interpretation_id": context.interpretation.id,
        "candidate_ids": tuple(candidate.id for candidate in context.candidates),
        "ambiguity_ids": tuple(item.id for item in context.interpretation.ambiguities),
        "reading_ids": tuple(item.id for item in context.interpretation.readings),
        "unresolved_candidate_ids": context.landscape.unresolved_candidate_ids,
        "diagnostic_codes": tuple(
            (item.candidate.id, diagnostic.code)
            for item in context.assessments
            for diagnostic in item.result.diagnostics
        ),
        "landscape_status": context.landscape.status.value,
        "varies_by_context": context.landscape.varies_by_context,
        "varies_by_formalization": context.landscape.varies_by_formalization,
        "admissible_disposition": admissible_disposition.value,
    }
    return profile.request(
        (
            "Choose the next workflow action for interpretation "
            f"{context.interpretation.id!r} with landscape "
            f"{context.landscape.status.value!r}."
        ),
        state=state,
        choices=_refinement_choices(admissible_disposition),
    )


def decide_clarification(
    context: ClarificationContext,
    *,
    profile: DecisionProfile,
    provider: TypedDecisionProvider,
) -> ClarificationDecisionResult:
    """Let a bounded provider refine a deterministic branch, never override it."""

    request = build_clarification_request(context, profile)
    admissible_disposition, _ = determine_disposition(context)
    decision = provider.decide(request)
    selected_choice = DeterministicDecisionPolicy(profile).select(decision)
    if selected_choice is None:
        return ClarificationDecisionResult(
            request=request,
            decision=decision,
            selected_choice=None,
            admissible_disposition=admissible_disposition,
            disposition=None,
        )
    if selected_choice not in request.choices:
        raise ValueError(
            f"Decision choice {selected_choice!r} is not admissible for "
            f"workflow branch {admissible_disposition.value!r}."
        )
    return ClarificationDecisionResult(
        request=request,
        decision=decision,
        selected_choice=selected_choice,
        admissible_disposition=admissible_disposition,
        disposition=admissible_disposition,
    )
