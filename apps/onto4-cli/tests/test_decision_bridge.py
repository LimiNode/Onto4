import pytest

from onto4.core import (
    AssessmentResult,
    AssessmentState,
    PredicateCall,
    PredicateExpr,
    SemanticStatus,
    Verdict,
)
from onto4.core.values import UnknownReason
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
        choices=(
            "NeedMeaningClarification",
            "NeedOntologyClarification",
            "NeedReferenceClarification",
            "NeedContextClarification",
            "NeedPresuppositionClarification",
            "SelectEvidencePath",
            "PresentResult",
            "ReportFailure",
            *(disposition.value for disposition in PipelineDisposition),
        ),
        abstention_policy=AbstentionPolicy.Allowed,
    )


def context(status=CrossCandidateStatus.FormalizationConflict, result=None):
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
    assessment = CandidateAssessment(
        candidate,
        "context",
        result
        or AssessmentResult(
            state=AssessmentState.Assessed,
            semantic_status=SemanticStatus.Admitted,
            verdict=Verdict.T,
            evidence=None,
        ),
    )
    landscape = AssessmentLandscape(
        assessments=(assessment,),
        status=status,
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
    assert set(request.choices).issubset(decision_profile.choices)
    assert request.state["interpretation_id"] == "interpretation"
    assert request.state["landscape_status"] == "FormalizationConflict"
    assert request.choices == (
        "NeedMeaningClarification",
        "NeedOntologyClarification",
        "NeedReferenceClarification",
        "NeedContextClarification",
        "NeedPresuppositionClarification",
    )


def test_bridge_maps_bounded_choice_to_workflow_disposition():
    decision_profile = profile()
    request = build_clarification_request(context(), decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "NeedMeaningClarification")},
    )

    result = decide_clarification(
        context(), profile=decision_profile, provider=provider
    )

    assert result.selected_choice == "NeedMeaningClarification"
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


def test_formalization_conflict_rejects_provider_complete_override():
    decision_profile = profile()
    request = build_clarification_request(context(), decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "Complete")},
    )

    with pytest.raises(ValueError, match="not admissible"):
        decide_clarification(
            context(), profile=decision_profile, provider=provider
        )


def test_invalid_request_rejects_provider_clarification_override():
    decision_profile = profile()
    invalid_context = context(status=CrossCandidateStatus.InvalidRequest)
    request = build_clarification_request(invalid_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "AskClarification")},
    )

    with pytest.raises(ValueError, match="not admissible"):
        decide_clarification(
            invalid_context, profile=decision_profile, provider=provider
        )


def test_evidence_gap_rejects_provider_complete_override():
    decision_profile = profile()
    evidence_context = context(
        status=CrossCandidateStatus.StableAcrossCandidates,
        result=AssessmentResult(
            state=AssessmentState.Assessed,
            semantic_status=SemanticStatus.Admitted,
            verdict=Verdict.U,
            evidence=None,
            unknown_reasons=(UnknownReason.InsufficientEvidence,),
        ),
    )
    request = build_clarification_request(evidence_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "Complete")},
    )

    with pytest.raises(ValueError, match="not admissible"):
        decide_clarification(
            evidence_context, profile=decision_profile, provider=provider
        )
