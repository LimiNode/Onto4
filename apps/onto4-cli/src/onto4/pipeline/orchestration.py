"""Named entry points for deterministic orchestration passes."""

from __future__ import annotations

from dataclasses import dataclass

from onto4.providers import DecisionProfile, TypedDecisionProvider
from onto4.reasoning import (
    ClarificationContext,
    ClarificationTurn,
    InterpretationSpace,
    TransitionAwareClarificationPolicy,
)

from .ask import AskResult, ask
from .decision_bridge import (
    ClarificationQuestionDecision,
    decide_clarification_question,
)


@dataclass(frozen=True)
class ClarificationTurnResult:
    """A bounded question decision and, when answered, its successor snapshot."""

    decision: ClarificationQuestionDecision
    successor: InterpretationSpace | None
    turn: ClarificationTurn | None


def orchestrate_once(*args, **kwargs) -> AskResult:
    """Run one interpretation-to-formalization-to-assessment pass."""

    return ask(*args, **kwargs)


def decide_clarification_turn(
    context: ClarificationContext,
    *,
    profile: DecisionProfile,
    provider: TypedDecisionProvider,
    clarification_policy: TransitionAwareClarificationPolicy,
    answer: str | None = None,
) -> ClarificationTurnResult:
    """Resolve one question and optionally record its immutable transition.

    A missing answer leaves the question pending. The function does not run a
    new assessment pass; callers must explicitly assess the returned successor
    interpretation in the next workflow iteration.
    """

    decision = decide_clarification_question(
        context,
        profile=profile,
        provider=provider,
        clarification_policy=clarification_policy,
    )
    question = decision.question
    if question is None:
        if answer is not None:
            raise ValueError("An answer cannot be recorded without a question.")
        return ClarificationTurnResult(decision, None, None)
    if answer is None:
        return ClarificationTurnResult(decision, None, None)
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
    return ClarificationTurnResult(decision, successor, turn)


__all__ = [
    "AskResult",
    "ClarificationTurnResult",
    "decide_clarification_turn",
    "orchestrate_once",
]
