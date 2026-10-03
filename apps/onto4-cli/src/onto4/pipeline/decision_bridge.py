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


@dataclass(frozen=True)
class ClarificationDecisionResult:
    request: TypedDecisionRequest
    decision: TypedDecision
    selected_choice: str | None
    disposition: PipelineDisposition | None


def build_clarification_request(
    context: ClarificationContext,
    profile: DecisionProfile,
) -> TypedDecisionRequest:
    """Encode meta-level clarification state as a bounded typed request."""

    state: Mapping[str, object] = {
        "interpretation_id": context.interpretation.id,
        "candidate_ids": tuple(candidate.id for candidate in context.candidates),
        "landscape_status": context.landscape.status.value,
        "varies_by_context": context.landscape.varies_by_context,
        "varies_by_formalization": context.landscape.varies_by_formalization,
    }
    return profile.request(
        (
            "Choose the next workflow action for interpretation "
            f"{context.interpretation.id!r} with landscape "
            f"{context.landscape.status.value!r}."
        ),
        state=state,
    )


def decide_clarification(
    context: ClarificationContext,
    *,
    profile: DecisionProfile,
    provider: TypedDecisionProvider,
) -> ClarificationDecisionResult:
    """Let a bounded provider suggest workflow action, never an Onto4 verdict."""

    request = build_clarification_request(context, profile)
    decision = provider.decide(request)
    selected_choice = DeterministicDecisionPolicy(profile).select(decision)
    if selected_choice is None:
        return ClarificationDecisionResult(
            request=request,
            decision=decision,
            selected_choice=None,
            disposition=None,
        )
    try:
        disposition = PipelineDisposition(selected_choice)
    except ValueError as exc:
        raise ValueError(
            f"Decision choice {selected_choice!r} is not a workflow disposition."
        ) from exc
    return ClarificationDecisionResult(
        request=request,
        decision=decision,
        selected_choice=selected_choice,
        disposition=disposition,
    )
