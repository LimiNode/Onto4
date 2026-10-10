"""Named entry points for deterministic orchestration passes."""

from __future__ import annotations

from dataclasses import dataclass

from onto4.providers import DecisionProfile, TypedDecisionProvider
from onto4.reasoning import (
    ClarificationContext,
    ClarificationTurn,
    InterpretationSpace,
    PipelineDisposition,
    TransitionAwareClarificationPolicy,
)

from .ask import AskResult, ask
from .decision_bridge import (
    CLARIFICATION_KIND_BY_REFINEMENT,
    ClarificationQuestionDecision,
    decide_clarification_question,
)


@dataclass(frozen=True)
class ClarificationTurnResult:
    """A bounded question decision and, when answered, its successor snapshot."""

    decision: ClarificationQuestionDecision
    successor: InterpretationSpace | None
    turn: ClarificationTurn | None
    pending: "PendingClarification" | None = None


@dataclass(frozen=True)
class PendingClarification:
    """Immutable question identity carried from issuance to answer."""

    interpretation_id: str
    decision: ClarificationQuestionDecision


def orchestrate_once(*args, **kwargs) -> AskResult:
    """Run one interpretation-to-formalization-to-assessment pass."""

    return ask(*args, **kwargs)


def decide_clarification_turn(
    context: ClarificationContext,
    *,
    profile: DecisionProfile | None = None,
    provider: TypedDecisionProvider | None = None,
    clarification_policy: TransitionAwareClarificationPolicy,
    answer: str | None = None,
    pending: PendingClarification | None = None,
) -> ClarificationTurnResult:
    """Issue a pending question, or apply an already-issued answer.

    The issuance path calls the provider once and returns a pending object.
    The answer path requires that object and never calls the provider again.
    The function does not run a new assessment pass; callers must explicitly
    assess the returned successor interpretation in the next iteration.
    """

    if pending is None:
        if profile is None or provider is None:
            raise ValueError(
                "profile and provider are required when issuing a clarification."
            )
        if answer is not None:
            raise ValueError(
                "An answer requires the PendingClarification returned at issuance."
            )
        decision = decide_clarification_question(
            context,
            profile=profile,
            provider=provider,
            clarification_policy=clarification_policy,
        )
        issued_pending = (
            PendingClarification(context.interpretation.id, decision)
            if decision.question is not None
            else None
        )
        return ClarificationTurnResult(decision, None, None, issued_pending)

    return apply_clarification_answer(
        context,
        pending=pending,
        answer=answer,
        clarification_policy=clarification_policy,
    )


def apply_clarification_answer(
    context: ClarificationContext,
    *,
    pending: PendingClarification,
    answer: str | None,
    clarification_policy: TransitionAwareClarificationPolicy,
) -> ClarificationTurnResult:
    """Apply an answer to the exact immutable question previously issued."""

    if pending.interpretation_id != context.interpretation.id:
        raise ValueError(
            "Pending clarification belongs to a different interpretation."
        )
    decision = pending.decision
    question = decision.question
    if question is None:
        raise ValueError("Pending clarification does not contain a question.")
    if decision.issued_question_id != question.id:
        raise ValueError("Pending clarification question id provenance is inconsistent.")
    if decision.issued_question_kind is not question.kind:
        raise ValueError(
            "Pending clarification question kind provenance is inconsistent."
        )
    result = decision.decision_result
    if result.request.state.get("interpretation_id") != pending.interpretation_id:
        raise ValueError("Pending decision interpretation provenance is inconsistent.")
    if result.disposition is not PipelineDisposition.AskClarification:
        raise ValueError("Pending decision is not an AskClarification branch.")
    selected_choice = result.selected_choice
    if selected_choice not in result.request.choices:
        raise ValueError("Pending decision refinement is not in its request choices.")
    expected_kind = CLARIFICATION_KIND_BY_REFINEMENT.get(selected_choice)
    if expected_kind is None or expected_kind is not question.kind:
        raise ValueError("Pending decision refinement does not match its question kind.")
    if answer is None:
        return ClarificationTurnResult(decision, None, None, pending)
    if not answer:
        raise ValueError("A clarification answer must not be empty.")
    if question.choices and answer not in question.choices:
        raise ValueError(
            f"Answer {answer!r} is not one of the clarification choices "
            f"{question.choices!r}."
        )
    successor, turn = clarification_policy.successor(
        interpretation=context.interpretation,
        question=question,
        answer=answer,
    )
    expected_turn = ClarificationTurn(
        previous_interpretation_id=context.interpretation.id,
        question_id=question.id,
        answer=answer,
        successor_interpretation_id=successor.id,
    )
    if turn != expected_turn:
        raise ValueError(
            "Clarification transition returned inconsistent turn provenance."
        )
    return ClarificationTurnResult(decision, successor, turn, pending)


__all__ = [
    "AskResult",
    "PendingClarification",
    "ClarificationTurnResult",
    "apply_clarification_answer",
    "decide_clarification_turn",
    "orchestrate_once",
]
