from dataclasses import replace

import pytest

from onto4.core import (
    AssessmentResult,
    AssessmentState,
    PredicateCall,
    PredicateExpr,
    SemanticStatus,
    Verdict,
)
from onto4.pipeline import (
    ClarificationSession,
    apply_clarification_answer,
    answer_session_clarification,
    build_clarification_request,
    issue_session_clarification,
)
from onto4.providers import (
    AbstentionPolicy,
    DecisionProfile,
    FixtureDecisionProvider,
    TypedDecision,
)
from onto4.reasoning import (
    AssessmentLandscape,
    CandidateAssessment,
    ClarificationContext,
    ClarificationState,
    ConceptualDepth,
    CrossCandidateStatus,
    FormalizationCandidate,
    FixtureClarificationPolicy,
    InterpretationSpace,
)


def clarification_context(
    interpretation: InterpretationSpace | None = None,
) -> ClarificationContext:
    interpretation = interpretation or InterpretationSpace(
        id="interpretation",
        source_text="Question",
        conceptual_depth=ConceptualDepth.Philosophical,
    )
    candidate = FormalizationCandidate(
        id="candidate",
        label="candidate",
        formalization_id="formalization",
        context_id="context",
        formalization=PredicateExpr(PredicateCall("a", ())),
    )
    assessment = CandidateAssessment(
        candidate=candidate,
        context_id="context",
        result=AssessmentResult(
            state=AssessmentState.Assessed,
            semantic_status=SemanticStatus.Admitted,
            verdict=Verdict.T,
            evidence=None,
        ),
    )
    return ClarificationContext(
        interpretation=interpretation,
        candidates=(candidate,),
        assessments=(assessment,),
        landscape=AssessmentLandscape(
            assessments=(assessment,),
            status=CrossCandidateStatus.FormalizationConflict,
        ),
    )


def decision_profile() -> DecisionProfile:
    return DecisionProfile(
        id="clarification-session",
        version="1",
        choices=("NeedFormalizationClarification",),
        abstention_policy=AbstentionPolicy.Allowed,
    )


def provider_for(
    context: ClarificationContext,
    profile: DecisionProfile,
    *,
    abstained: bool = False,
) -> FixtureDecisionProvider:
    request = build_clarification_request(context, profile)
    decision = TypedDecision(
        profile_id=profile.id,
        profile_version=profile.version,
        choice=None if abstained else "NeedFormalizationClarification",
        abstained=abstained,
    )
    return FixtureDecisionProvider(profile, {request.question: decision})


def issue(
    session: ClarificationSession,
    context: ClarificationContext,
    policy: FixtureClarificationPolicy,
    *,
    abstained: bool = False,
):
    profile = decision_profile()
    return issue_session_clarification(
        session,
        context,
        profile=profile,
        provider=provider_for(context, profile, abstained=abstained),
        clarification_policy=policy,
    )


def test_session_issuance_tracks_one_pending_question_without_mutating_history():
    context = clarification_context()
    session = ClarificationSession(context.interpretation)

    issued = issue(session, context, FixtureClarificationPolicy())

    assert issued.session is not session
    assert issued.session.interpretation is session.interpretation
    assert issued.session.history is session.history
    assert issued.session.pending is issued.turn_result.pending
    assert issued.session.pending is not None


def test_session_answer_advances_snapshot_records_history_and_clears_pending():
    context = clarification_context()
    question = FixtureClarificationPolicy().choose(context)
    successor = InterpretationSpace(
        id="successor",
        source_text="Question clarified",
        conceptual_depth=ConceptualDepth.Philosophical,
    )
    policy = FixtureClarificationPolicy(
        transitions={(context.interpretation.id, question.id, "candidate"): successor}
    )
    issued = issue(ClarificationSession(context.interpretation), context, policy)

    answered = answer_session_clarification(
        issued.session,
        context,
        answer="candidate",
        clarification_policy=policy,
    )

    assert answered.session.interpretation is successor
    assert answered.session.pending is None
    assert answered.session.history.turns == (answered.turn_result.turn,)
    assert answered.turn_result.successor is successor


def test_session_carries_continuous_history_across_two_answered_turns():
    first_context = clarification_context()
    question = FixtureClarificationPolicy().choose(first_context)
    second_interpretation = InterpretationSpace(
        id="second",
        source_text="Question clarified once",
        conceptual_depth=ConceptualDepth.Philosophical,
    )
    third_interpretation = InterpretationSpace(
        id="third",
        source_text="Question clarified twice",
        conceptual_depth=ConceptualDepth.Philosophical,
    )
    policy = FixtureClarificationPolicy(
        transitions={
            (
                first_context.interpretation.id,
                question.id,
                "candidate",
            ): second_interpretation,
            (second_interpretation.id, question.id, "candidate"): third_interpretation,
        }
    )
    first_issued = issue(
        ClarificationSession(first_context.interpretation), first_context, policy
    )
    first_answered = answer_session_clarification(
        first_issued.session,
        first_context,
        answer="candidate",
        clarification_policy=policy,
    )
    second_context = clarification_context(second_interpretation)
    second_issued = issue(first_answered.session, second_context, policy)

    second_answered = answer_session_clarification(
        second_issued.session,
        second_context,
        answer="candidate",
        clarification_policy=policy,
    )

    assert second_answered.session.interpretation is third_interpretation
    assert len(second_answered.session.history.turns) == 2
    assert (
        second_answered.session.history.turns[0].successor_interpretation_id
        == second_answered.session.history.turns[1].previous_interpretation_id
        == second_interpretation.id
    )


def test_session_answer_none_preserves_exact_pending_state():
    context = clarification_context()
    policy = FixtureClarificationPolicy()
    issued = issue(ClarificationSession(context.interpretation), context, policy)

    waiting = answer_session_clarification(
        issued.session,
        context,
        answer=None,
        clarification_policy=policy,
    )

    assert waiting.session is issued.session
    assert waiting.turn_result.pending is issued.session.pending
    assert waiting.turn_result.turn is None
    assert waiting.turn_result.successor is None


def test_session_abstention_is_a_no_op():
    context = clarification_context()
    session = ClarificationSession(context.interpretation)

    result = issue(
        session,
        context,
        FixtureClarificationPolicy(),
        abstained=True,
    )

    assert result.session is session
    assert result.turn_result.pending is None


def test_session_rejects_second_issuance_while_question_is_pending():
    context = clarification_context()
    policy = FixtureClarificationPolicy()
    issued = issue(ClarificationSession(context.interpretation), context, policy)

    with pytest.raises(ValueError, match="already has a pending"):
        issue(issued.session, context, policy)


def test_session_requires_the_exact_current_interpretation_snapshot():
    context = clarification_context()
    session = ClarificationSession(context.interpretation)
    changed_snapshot = replace(context.interpretation, source_text="Changed question")
    mismatched_context = replace(context, interpretation=changed_snapshot)

    with pytest.raises(ValueError, match="does not match the session"):
        issue(session, mismatched_context, FixtureClarificationPolicy())


def test_session_rejects_history_whose_tail_is_not_the_current_interpretation():
    context = clarification_context()
    history = ClarificationState().record(
        previous_interpretation_id="previous",
        question_id="question",
        answer="answer",
        successor_interpretation_id="different-successor",
    )

    with pytest.raises(ValueError, match="does not match its history"):
        ClarificationSession(context.interpretation, history=history)


def test_session_rejects_pending_from_stale_same_id_snapshot():
    original = clarification_context()
    profile = decision_profile()
    issued = issue_session_clarification(
        ClarificationSession(original.interpretation),
        original,
        profile=profile,
        provider=provider_for(original, profile),
        clarification_policy=FixtureClarificationPolicy(),
    )
    stale_snapshot = replace(
        original.interpretation,
        source_text="Changed question",
    )

    with pytest.raises(ValueError, match="snapshot"):
        ClarificationSession(stale_snapshot, pending=issued.session.pending)


def test_answer_rejects_pending_from_stale_same_id_snapshot():
    original = clarification_context()
    profile = decision_profile()
    issued = issue_session_clarification(
        ClarificationSession(original.interpretation),
        original,
        profile=profile,
        provider=provider_for(original, profile),
        clarification_policy=FixtureClarificationPolicy(),
    )
    changed_snapshot = replace(
        original.interpretation,
        readings=(),
        source_text="Changed question",
    )
    changed_context = clarification_context(changed_snapshot)

    with pytest.raises(ValueError, match="snapshot"):
        apply_clarification_answer(
            changed_context,
            pending=issued.session.pending,
            answer="candidate",
            clarification_policy=FixtureClarificationPolicy(),
        )


def test_session_rejects_answer_without_a_pending_question():
    context = clarification_context()

    with pytest.raises(ValueError, match="no pending question"):
        answer_session_clarification(
            ClarificationSession(context.interpretation),
            context,
            answer="candidate",
            clarification_policy=FixtureClarificationPolicy(),
        )
