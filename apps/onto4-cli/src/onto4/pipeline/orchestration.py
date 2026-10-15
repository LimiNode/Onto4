"""Named entry points for deterministic orchestration passes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from onto4.core import AssessmentContext
from onto4.providers import (
    DecisionProfile,
    FormalizationProvider,
    TypedDecisionProvider,
)
from onto4.reasoning import (
    ClarificationContext,
    ClarificationPolicy,
    ClarificationState,
    ClarificationTurn,
    InterpretationSpace,
    PipelineDisposition,
    TransitionAwareClarificationPolicy,
)

from .ask import AskResult, ask, assess_interpretation, assess_interpretation_per_reading
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
    prepared: "PreparedClarificationTransition | None" = None


@dataclass(frozen=True)
class PreparedClarificationTransition:
    """Validated provider transition awaiting orchestration commit."""

    successor: InterpretationSpace
    turn: ClarificationTurn
    progress: object | None = None


@dataclass(frozen=True)
class PendingClarification:
    """Immutable question identity carried from issuance to answer."""

    interpretation: InterpretationSpace
    decision: ClarificationQuestionDecision

    @property
    def interpretation_id(self) -> str:
        """Compatibility view of the bound snapshot's stable identifier."""

        return self.interpretation.id


@dataclass(frozen=True)
class ClarificationSession:
    """Current interpretation, history, and at most one issued question."""

    interpretation: InterpretationSpace
    history: ClarificationState = field(default_factory=ClarificationState)
    pending: PendingClarification | None = None

    def __post_init__(self) -> None:
        if (
            self.history.turns
            and self.history.turns[-1].successor_interpretation_id
            != self.interpretation.id
        ):
            raise ValueError(
                "Clarification session interpretation does not match its history."
            )
        if (
            self.pending is not None
            and self.pending.interpretation != self.interpretation
        ):
            raise ValueError(
                "Pending clarification snapshot does not match the session interpretation."
            )


@dataclass(frozen=True)
class ClarificationSessionResult:
    """Session state paired with the bounded result that produced it."""

    session: ClarificationSession
    turn_result: ClarificationTurnResult


@dataclass(frozen=True)
class SessionAssessment:
    """One fresh assessment pass bound to its exact interpretation snapshot."""

    interpretation: InterpretationSpace
    ask_result: AskResult

    def __post_init__(self) -> None:
        if self.ask_result.interpretation != self.interpretation:
            raise ValueError(
                "Session assessment snapshot does not match its AskResult."
            )

    def clarification_context(self) -> ClarificationContext:
        """Expose the context produced by this exact assessment pass."""

        result = self.ask_result
        return ClarificationContext(
            interpretation=result.interpretation,
            candidates=result.candidates,
            assessments=result.assessments,
            landscape=result.landscape,
        )


@dataclass(frozen=True)
class ReasoningSession:
    """Clarification state paired with its latest explicit assessment, if any."""

    clarification: ClarificationSession
    assessment: SessionAssessment | None = None

    def __post_init__(self) -> None:
        if self.assessment is not None:
            require_current_session_assessment(self.clarification, self.assessment)
        if self.clarification.pending is not None and self.assessment is None:
            raise ValueError(
                "A reasoning session with a pending question requires a current assessment."
            )


@dataclass(frozen=True)
class ReasoningSessionResult:
    """Immutable reasoning state and the optional clarification transition result."""

    session: ReasoningSession
    clarification: ClarificationSessionResult | None = None


def require_current_session_assessment(
    session: ClarificationSession,
    assessment: SessionAssessment,
) -> AskResult:
    """Return an assessment only when it belongs to the session snapshot."""

    if assessment.interpretation != session.interpretation:
        raise ValueError(
            "Session assessment snapshot does not match the current interpretation."
        )
    return assessment.ask_result


def start_reasoning_session(
    session: ClarificationSession,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> ReasoningSessionResult:
    """Create a reasoning session with one explicit initial assessment."""

    assessment = reassess_session(
        session,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=clarification_policy,
    )
    return ReasoningSessionResult(ReasoningSession(session, assessment))


def start_reasoning_session_per_reading(
    session: ClarificationSession,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> ReasoningSessionResult:
    """Start a session using host-bound per-reading/context formalization."""

    assessment = reassess_session_per_reading(
        session,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=clarification_policy,
    )
    return ReasoningSessionResult(ReasoningSession(session, assessment))


def reassess_reasoning_session(
    session: ReasoningSession,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> ReasoningSessionResult:
    """Replace the latest assessment with a fresh pass for the current snapshot."""

    assessment = reassess_session(
        session.clarification,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=clarification_policy,
    )
    return ReasoningSessionResult(ReasoningSession(session.clarification, assessment))


def reassess_reasoning_session_per_reading(
    session: ReasoningSession,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> ReasoningSessionResult:
    """Replace the assessment using per-reading/context formalization."""

    assessment = reassess_session_per_reading(
        session.clarification,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=clarification_policy,
    )
    return ReasoningSessionResult(ReasoningSession(session.clarification, assessment))


def issue_reasoning_clarification(
    session: ReasoningSession,
    *,
    profile: DecisionProfile,
    provider: TypedDecisionProvider,
    clarification_policy: TransitionAwareClarificationPolicy,
) -> ReasoningSessionResult:
    """Issue one question from the current assessment without reassessing."""

    if session.assessment is None:
        raise ValueError("A current assessment is required to issue clarification.")
    require_current_session_assessment(session.clarification, session.assessment)
    result = issue_session_clarification(
        session.clarification,
        session.assessment.clarification_context(),
        profile=profile,
        provider=provider,
        clarification_policy=clarification_policy,
    )
    next_session = (
        session
        if result.session is session.clarification
        else ReasoningSession(result.session, session.assessment)
    )
    return ReasoningSessionResult(
        next_session,
        result,
    )


def answer_reasoning_clarification(
    session: ReasoningSession,
    *,
    answer: str | None,
    clarification_policy: TransitionAwareClarificationPolicy,
    allow_freeform_answers: bool = False,
) -> ReasoningSessionResult:
    """Apply the issued answer and invalidate assessment until explicit reassessment."""

    if session.assessment is None:
        raise ValueError("A current assessment is required to answer clarification.")
    require_current_session_assessment(session.clarification, session.assessment)
    result = answer_session_clarification(
        session.clarification,
        session.assessment.clarification_context(),
        answer=answer,
        clarification_policy=clarification_policy,
        allow_freeform_answers=allow_freeform_answers,
    )
    if result.session is session.clarification and result.turn_result.turn is None:
        return ReasoningSessionResult(session, result)
    next_assessment = session.assessment if result.turn_result.turn is None else None
    return ReasoningSessionResult(
        ReasoningSession(result.session, next_assessment),
        result,
    )


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
    allow_freeform_answers: bool = False,
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
            PendingClarification(context.interpretation, decision)
            if decision.question is not None
            else None
        )
        return ClarificationTurnResult(decision, None, None, issued_pending)

    return apply_clarification_answer(
        context,
        pending=pending,
        answer=answer,
        clarification_policy=clarification_policy,
        allow_freeform_answers=allow_freeform_answers,
    )


def apply_clarification_answer(
    context: ClarificationContext,
    *,
    pending: PendingClarification,
    answer: str | None,
    clarification_policy: TransitionAwareClarificationPolicy,
    allow_freeform_answers: bool = False,
) -> ClarificationTurnResult:
    """Apply an answer to the exact immutable question previously issued."""

    if pending is None:
        raise ValueError("PendingClarification is required to apply an answer.")
    if pending.interpretation != context.interpretation:
        raise ValueError(
            "Pending clarification snapshot does not match the current interpretation "
            "(different interpretation snapshot)."
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
    if (
        question.choices
        and not allow_freeform_answers
        and answer not in question.choices
    ):
        raise ValueError(
            f"Answer {answer!r} is not one of the clarification choices "
            f"{question.choices!r}."
        )
    prepare = getattr(clarification_policy, "prepare_successor", None)
    if prepare is not None:
        prepared = prepare(
            interpretation=context.interpretation,
            question=question,
            answer=answer,
        )
        successor, turn = prepared.successor, prepared.turn
    else:
        prepared = None
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
    return ClarificationTurnResult(decision, successor, turn, None, prepared)


def record_clarification_turn(
    history: ClarificationState,
    result: ClarificationTurnResult,
) -> ClarificationState:
    """Record exactly one answered turn, preserving pending/no-op states."""

    if result.turn is None:
        if result.successor is not None:
            raise ValueError(
                "A clarification result cannot have a successor without a turn."
            )
        return history
    if result.pending is not None or result.successor is None:
        raise ValueError(
            "An answered clarification result must clear pending and provide a successor."
        )
    turn = result.turn
    if result.successor.id != turn.successor_interpretation_id:
        raise ValueError(
            "Clarification turn successor provenance does not match the result snapshot."
        )
    return history.record(
        previous_interpretation_id=turn.previous_interpretation_id,
        question_id=turn.question_id,
        answer=turn.answer,
        successor_interpretation_id=turn.successor_interpretation_id,
    )


def issue_session_clarification(
    session: ClarificationSession,
    context: ClarificationContext,
    *,
    profile: DecisionProfile,
    provider: TypedDecisionProvider,
    clarification_policy: TransitionAwareClarificationPolicy,
) -> ClarificationSessionResult:
    """Issue at most one question for the session's exact current snapshot."""

    _require_current_session_context(session, context)
    if session.pending is not None:
        raise ValueError("Clarification session already has a pending question.")
    turn_result = decide_clarification_turn(
        context,
        profile=profile,
        provider=provider,
        clarification_policy=clarification_policy,
    )
    if turn_result.pending is None:
        return ClarificationSessionResult(session, turn_result)
    next_session = ClarificationSession(
        interpretation=session.interpretation,
        history=session.history,
        pending=turn_result.pending,
    )
    return ClarificationSessionResult(next_session, turn_result)


def answer_session_clarification(
    session: ClarificationSession,
    context: ClarificationContext,
    *,
    answer: str | None,
    clarification_policy: TransitionAwareClarificationPolicy,
    allow_freeform_answers: bool = False,
) -> ClarificationSessionResult:
    """Apply the session's issued question without invoking a provider."""

    _require_current_session_context(session, context)
    if session.pending is None:
        raise ValueError("Clarification session has no pending question to answer.")
    turn_result = apply_clarification_answer(
        context,
        pending=session.pending,
        answer=answer,
        clarification_policy=clarification_policy,
        allow_freeform_answers=allow_freeform_answers,
    )
    if turn_result.turn is None:
        return ClarificationSessionResult(session, turn_result)
    history = record_clarification_turn(session.history, turn_result)
    if turn_result.successor is None:
        raise ValueError("Answered clarification did not provide a successor.")
    next_session = ClarificationSession(
        interpretation=turn_result.successor,
        history=history,
        pending=None,
    )
    _commit_prepared_transition(clarification_policy, turn_result.prepared)
    return ClarificationSessionResult(next_session, turn_result)


def _commit_prepared_transition(
    clarification_policy: TransitionAwareClarificationPolicy,
    prepared: PreparedClarificationTransition | None,
) -> None:
    if prepared is None:
        return
    commit = getattr(clarification_policy, "commit_prepared", None)
    if commit is None:
        raise ValueError(
            "Clarification policy returned a prepared transition without a commit hook."
        )
    commit(prepared)


def reassess_session(
    session: ClarificationSession,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> SessionAssessment:
    """Run one explicit fresh pass for the session's current interpretation."""

    if session.pending is not None:
        raise ValueError(
            "Cannot reassess a clarification session while a question is pending."
        )
    result = assess_interpretation(
        session.interpretation,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=clarification_policy,
    )
    return SessionAssessment(session.interpretation, result)


def reassess_session_per_reading(
    session: ClarificationSession,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> SessionAssessment:
    """Run a fresh assessment using one request per reading/context pair."""

    if session.pending is not None:
        raise ValueError(
            "Cannot reassess a clarification session while a question is pending."
        )
    result = assess_interpretation_per_reading(
        session.interpretation,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=clarification_policy,
    )
    return SessionAssessment(session.interpretation, result)


def _require_current_session_context(
    session: ClarificationSession,
    context: ClarificationContext,
) -> None:
    if context.interpretation != session.interpretation:
        raise ValueError(
            "Clarification context does not match the session interpretation snapshot."
        )


__all__ = [
    "AskResult",
    "ClarificationSession",
    "ClarificationSessionResult",
    "ReasoningSession",
    "ReasoningSessionResult",
    "SessionAssessment",
    "PendingClarification",
    "ClarificationTurnResult",
    "PreparedClarificationTransition",
    "answer_session_clarification",
    "apply_clarification_answer",
    "decide_clarification_turn",
    "issue_session_clarification",
    "issue_reasoning_clarification",
    "orchestrate_once",
    "reassess_session",
    "reassess_reasoning_session",
    "reassess_reasoning_session_per_reading",
    "record_clarification_turn",
    "require_current_session_assessment",
    "answer_reasoning_clarification",
    "start_reasoning_session",
    "start_reasoning_session_per_reading",
]
