import pytest

from onto4.core import PredicateCall, PredicateExpr
from onto4.pipeline import build_clarification_request, decide_clarification
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
    ConceptualDepth,
    CrossCandidateStatus,
    FormalizationCandidate,
    InterpretationSpace,
    PipelineDisposition,
)


def profile():
    return DecisionProfile(
        id="clarification-disposition",
        version="1",
        choices=tuple(disposition.value for disposition in PipelineDisposition),
        abstention_policy=AbstentionPolicy.Allowed,
    )


def context():
    candidate = FormalizationCandidate(
        id="candidate",
        label="candidate",
        formalization_id="formalization",
        context_id="context",
        formalization=PredicateExpr(PredicateCall("a", ())),
    )
    interpretation = InterpretationSpace(
        id="interpretation",
        source_text="Question",
        conceptual_depth=ConceptualDepth.Philosophical,
    )
    assessment = CandidateAssessment(candidate, "context", object())
    landscape = AssessmentLandscape(
        assessments=(assessment,),
        status=CrossCandidateStatus.FormalizationConflict,
    )
    return ClarificationContext(
        interpretation=interpretation,
        candidates=(candidate,),
        assessments=(assessment,),
        landscape=landscape,
    )


def decision(decision_profile, choice=None, *, abstained=False):
    return TypedDecision(
        profile_id=decision_profile.id,
        profile_version=decision_profile.version,
        choice=choice,
        abstained=abstained,
    )


def test_bridge_builds_profile_scoped_meta_request():
    decision_profile = profile()
    request = build_clarification_request(context(), decision_profile)

    assert request.profile == decision_profile.id
    assert request.profile_version == decision_profile.version
    assert request.choices == decision_profile.choices
    assert request.state["interpretation_id"] == "interpretation"
    assert request.state["landscape_status"] == "FormalizationConflict"
    assert not any(choice in {"T", "F", "U", "C"} for choice in request.choices)


def test_bridge_maps_bounded_choice_to_workflow_disposition():
    decision_profile = profile()
    request = build_clarification_request(context(), decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "AskClarification")},
    )

    result = decide_clarification(
        context(), profile=decision_profile, provider=provider
    )

    assert result.selected_choice == "AskClarification"
    assert result.disposition is PipelineDisposition.AskClarification
    assert not hasattr(result.decision, "verdict")


def test_bridge_preserves_explicit_provider_abstention():
    decision_profile = profile()
    request = build_clarification_request(context(), decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, abstained=True)},
    )

    result = decide_clarification(
        context(), profile=decision_profile, provider=provider
    )

    assert result.decision.abstained is True
    assert result.selected_choice is None
    assert result.disposition is None


def test_provider_cannot_submit_onto4_verdict_as_bridge_choice():
    decision_profile = profile()
    request = build_clarification_request(context(), decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "T")},
    )

    with pytest.raises(ValueError, match="not valid"):
        decide_clarification(
            context(), profile=decision_profile, provider=provider
        )
