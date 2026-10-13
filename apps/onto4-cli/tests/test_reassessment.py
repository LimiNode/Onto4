from dataclasses import replace

import pytest

from onto4.core import (
    AssessmentContext,
    OntologyProfile,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    Verdict,
)
from onto4.core.evidence import AtomicVerdictStore
from onto4.pipeline import (
    ClarificationSession,
    SessionAssessment,
    assess_interpretation,
    build_clarification_request,
    issue_session_clarification,
    reassess_session,
    require_current_session_assessment,
    answer_session_clarification,
)
from onto4.providers import (
    AbstentionPolicy,
    DecisionProfile,
    FixtureDecisionProvider,
    FixtureFormalizationProvider,
    TypedDecision,
)
from onto4.reasoning import (
    AssessmentLandscape,
    CandidateAssessment,
    ClarificationContext,
    ConceptualDepth,
    CrossCandidateStatus,
    FormalizationCandidate,
    FixtureClarificationPolicy,
    InterpretationSpace,
    PipelineDisposition,
)


def atom(name: str) -> PredicateExpr:
    return PredicateExpr(PredicateCall(name, ()))


def assessment_context(verdicts: dict[str, Verdict]) -> AssessmentContext:
    return AssessmentContext(
        ontology=OntologyProfile(
            name="fixture",
            predicates={name: PredicateSignature(()) for name in verdicts},
        ),
        verdicts=AtomicVerdictStore(
            {f"{name}()": verdict for name, verdict in verdicts.items()}
        ),
    )


def candidate(
    identifier: str,
    formalization_id: str,
    expression: PredicateExpr,
) -> FormalizationCandidate:
    return FormalizationCandidate(
        id=identifier,
        label=identifier,
        formalization_id=formalization_id,
        context_id="fixture",
        formalization=expression,
    )


def profile() -> DecisionProfile:
    return DecisionProfile(
        id="reassessment",
        version="1",
        choices=("NeedFormalizationClarification",),
        abstention_policy=AbstentionPolicy.Allowed,
    )


def provider_for(
    context: ClarificationContext,
    decision_profile: DecisionProfile,
    *,
    abstained: bool = False,
) -> FixtureDecisionProvider:
    request = build_clarification_request(context, decision_profile)
    return FixtureDecisionProvider(
        decision_profile,
        {
            request.question: TypedDecision(
                profile_id=decision_profile.id,
                profile_version=decision_profile.version,
                choice=None if abstained else "NeedFormalizationClarification",
                abstained=abstained,
            )
        },
    )


def interpretation(identifier: str) -> InterpretationSpace:
    return InterpretationSpace(
        id=identifier,
        source_text="Question",
        conceptual_depth=ConceptualDepth.Philosophical,
    )


def context_from(assessment: SessionAssessment) -> ClarificationContext:
    result = assessment.ask_result
    return ClarificationContext(
        interpretation=result.interpretation,
        candidates=result.candidates,
        assessments=result.assessments,
        landscape=result.landscape,
    )


def test_reassessment_loop_replaces_stale_assessment_after_answer():
    initial = interpretation("initial")
    successor = interpretation("successor")
    initial_candidates = (
        candidate("first", "formal-first", atom("a")),
        candidate("second", "formal-second", atom("b")),
    )
    resolved_candidate = candidate("resolved", "formal-resolved", atom("a"))
    formalization_provider = FixtureFormalizationProvider(
        {
            initial.id: initial_candidates,
            successor.id: (resolved_candidate,),
        }
    )
    contexts = {"fixture": assessment_context({"a": Verdict.T, "b": Verdict.F})}
    policy = FixtureClarificationPolicy(
        transitions={("initial", "formalization:disambiguate", "first"): successor}
    )
    session = ClarificationSession(initial)

    first_assessment = reassess_session(
        session,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=policy,
    )
    first_context = context_from(first_assessment)
    assert first_assessment.ask_result.landscape.status is CrossCandidateStatus.FormalizationConflict
    assert first_assessment.ask_result.disposition is PipelineDisposition.AskClarification
    assert tuple(candidate.id for candidate in first_assessment.ask_result.candidates) == (
        "first",
        "second",
    )

    decision_profile = profile()
    issued = issue_session_clarification(
        session,
        first_context,
        profile=decision_profile,
        provider=provider_for(first_context, decision_profile),
        clarification_policy=policy,
    )
    answered = answer_session_clarification(
        issued.session,
        first_context,
        answer="first",
        clarification_policy=policy,
    )
    assert answered.session.interpretation is successor

    with pytest.raises(ValueError, match="current interpretation"):
        require_current_session_assessment(answered.session, first_assessment)

    second_assessment = reassess_session(
        answered.session,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=policy,
    )
    assert second_assessment.interpretation is successor
    assert second_assessment.ask_result.landscape.status is CrossCandidateStatus.StableAcrossCandidates
    assert second_assessment.ask_result.disposition is PipelineDisposition.Complete
    assert tuple(candidate.id for candidate in second_assessment.ask_result.candidates) == (
        "resolved",
    )


def test_reassessment_rejects_pending_session():
    initial = interpretation("initial")
    formalization_provider = FixtureFormalizationProvider(
        {initial.id: (candidate("first", "formal-first", atom("a")),)}
    )
    contexts = {"fixture": assessment_context({"a": Verdict.T})}
    session = ClarificationSession(initial)
    baseline = reassess_session(
        session,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=FixtureClarificationPolicy(),
    )
    pending_context = replace(
        context_from(baseline),
        landscape=AssessmentLandscape(
            assessments=baseline.ask_result.assessments,
            status=CrossCandidateStatus.FormalizationConflict,
        ),
    )
    decision_profile = profile()
    issued = issue_session_clarification(
        session,
        pending_context,
        profile=decision_profile,
        provider=provider_for(pending_context, decision_profile),
        clarification_policy=FixtureClarificationPolicy(),
    )

    with pytest.raises(ValueError, match="pending"):
        reassess_session(
            issued.session,
            formalization_provider=formalization_provider,
            contexts=contexts,
            clarification_policy=FixtureClarificationPolicy(),
        )

def test_reassessment_builds_fresh_result_without_reusing_old_candidates():
    initial = interpretation("initial")
    provider = FixtureFormalizationProvider(
        {initial.id: (candidate("fresh", "formal-fresh", atom("a")),)}
    )
    contexts = {"fixture": assessment_context({"a": Verdict.T})}

    result = assess_interpretation(
        initial,
        formalization_provider=provider,
        contexts=contexts,
        clarification_policy=FixtureClarificationPolicy(),
    )

    assert result.interpretation is initial
    assert result.candidates[0].id == "fresh"
    assert result.assessments[0].candidate is result.candidates[0]


def test_session_assessment_rejects_mismatched_snapshot_even_with_same_id():
    initial = interpretation("initial")
    provider = FixtureFormalizationProvider(
        {initial.id: (candidate("fresh", "formal-fresh", atom("a")),)}
    )
    contexts = {"fixture": assessment_context({"a": Verdict.T})}
    result = assess_interpretation(
        initial,
        formalization_provider=provider,
        contexts=contexts,
        clarification_policy=FixtureClarificationPolicy(),
    )

    with pytest.raises(ValueError, match="does not match"):
        SessionAssessment(replace(initial, source_text="Changed question"), result)


def test_abstention_does_not_advance_session_before_reassessment():
    initial = interpretation("initial")
    candidate_value = candidate("first", "formal-first", atom("a"))
    contexts = {"fixture": assessment_context({"a": Verdict.T})}
    formalization_provider = FixtureFormalizationProvider(
        {initial.id: (candidate_value,)}
    )
    assessment = reassess_session(
        ClarificationSession(initial),
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=FixtureClarificationPolicy(),
    )
    clarification_context = replace(
        context_from(assessment),
        landscape=AssessmentLandscape(
            assessments=assessment.ask_result.assessments,
            status=CrossCandidateStatus.FormalizationConflict,
        ),
    )
    session = ClarificationSession(initial)
    decision_profile = profile()
    issued = issue_session_clarification(
        session,
        clarification_context,
        profile=decision_profile,
        provider=provider_for(
            clarification_context,
            decision_profile,
            abstained=True,
        ),
        clarification_policy=FixtureClarificationPolicy(),
    )

    assert issued.session is session
    assert issued.turn_result.pending is None
