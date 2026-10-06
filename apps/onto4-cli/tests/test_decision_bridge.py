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
from onto4.core.admission import Diagnostic
from onto4.pipeline import build_clarification_request, decide_clarification
from onto4.providers import (
    AbstentionPolicy,
    DecisionProfile,
    FixtureDecisionProvider,
    TypedDecision,
)
from onto4.reasoning import (
    AssessmentLandscape,
    Ambiguity,
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
            "NeedFormalizationClarification",
            "SelectEvidencePath",
            "PresentResult",
            "ReportFailure",
            *(disposition.value for disposition in PipelineDisposition),
        ),
        abstention_policy=AbstentionPolicy.Allowed,
    )


def context(
    status=CrossCandidateStatus.FormalizationConflict,
    result=None,
    *,
    reading_id=None,
    ambiguities=(),
    unresolved_candidate_ids=(),
):
    candidate = FormalizationCandidate(
        id="candidate",
        label="candidate",
        formalization_id="formalization",
        context_id="context",
        formalization=PredicateExpr(PredicateCall("a", ())),
        reading_id=reading_id,
    )
    interpretation = InterpretationSpace(
        id="interpretation",
        source_text="Question",
        conceptual_depth=ConceptualDepth.Philosophical,
        ambiguities=ambiguities,
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
        unresolved_candidate_ids=unresolved_candidate_ids,
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
    assert request.choices == ("NeedFormalizationClarification",)


def test_bridge_maps_bounded_choice_to_workflow_disposition():
    decision_profile = profile()
    request = build_clarification_request(context(), decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )

    result = decide_clarification(
        context(), profile=decision_profile, provider=provider
    )

    assert result.selected_choice == "NeedFormalizationClarification"
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
    assert result.request.choices == ("NeedFormalizationClarification",)
    assert result.admissible_disposition is PipelineDisposition.AskClarification
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


def test_formalization_conflict_rejects_unjustified_reference_refinement():
    decision_profile = profile()
    request = build_clarification_request(context(), decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "NeedReferenceClarification")},
    )

    with pytest.raises(ValueError, match="not admissible"):
        decide_clarification(context(), profile=decision_profile, provider=provider)


def test_formalization_conflict_with_reading_provenance_exposes_meaning_only():
    decision_profile = profile()
    reading_context = context(reading_id="reading:one")
    request = build_clarification_request(reading_context, decision_profile)

    assert request.choices == ("NeedMeaningClarification",)


def test_context_dependence_exposes_context_and_rejects_meaning():
    decision_profile = profile()
    first = context(
        status=CrossCandidateStatus.ContextDependent,
        result=AssessmentResult(
            state=AssessmentState.Assessed,
            semantic_status=SemanticStatus.Admitted,
            verdict=Verdict.T,
            evidence=None,
        ),
    ).assessments[0]
    second_candidate = FormalizationCandidate(
        id="candidate-2",
        label="candidate-2",
        formalization_id="formalization",
        context_id="context-2",
        formalization=first.candidate.formalization,
    )
    second = CandidateAssessment(
        second_candidate,
        "context-2",
        AssessmentResult(
            state=AssessmentState.Assessed,
            semantic_status=SemanticStatus.Admitted,
            verdict=Verdict.F,
            evidence=None,
        ),
    )
    dependent = ClarificationContext(
        interpretation=context().interpretation,
        candidates=(first.candidate, second_candidate),
        assessments=(first, second),
        landscape=AssessmentLandscape(
            assessments=(first, second),
            status=CrossCandidateStatus.ContextDependent,
        ),
    )
    request = build_clarification_request(dependent, decision_profile)
    assert request.choices == ("NeedContextClarification",)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "NeedMeaningClarification")},
    )
    with pytest.raises(ValueError, match="not admissible"):
        decide_clarification(dependent, profile=decision_profile, provider=provider)


@pytest.mark.parametrize(
    ("diagnostic_code", "expected_choice"),
    (
        ("unknown_symbol", "NeedReferenceClarification"),
        ("unknown_predicate", "NeedMeaningClarification"),
        ("ontology_unresolved", "NeedOntologyClarification"),
        ("presupposition_unresolved", "NeedPresuppositionClarification"),
    ),
)
def test_unresolved_diagnostic_exposes_matching_refinement(
    diagnostic_code, expected_choice
):
    decision_profile = profile()
    unresolved = context(
        status=CrossCandidateStatus.FormalizationUnresolved,
        result=AssessmentResult(
            state=AssessmentState.FormalizationUnresolved,
            semantic_status=None,
            verdict=None,
            evidence=None,
            diagnostics=(Diagnostic(diagnostic_code, "unresolved cause"),),
        ),
        unresolved_candidate_ids=("candidate",),
    )
    request = build_clarification_request(unresolved, decision_profile)
    assert request.choices == (expected_choice,)


def test_bare_unresolved_formalization_exposes_formalization_refinement():
    decision_profile = profile()
    unresolved = context(
        status=CrossCandidateStatus.FormalizationUnresolved,
        result=AssessmentResult(
            state=AssessmentState.FormalizationUnresolved,
            semantic_status=None,
            verdict=None,
            evidence=None,
            diagnostics=(
                Diagnostic("formalization_unresolved", "no formalization"),
            ),
        ),
        unresolved_candidate_ids=("candidate",),
    )
    request = build_clarification_request(unresolved, decision_profile)
    assert request.choices == ("NeedFormalizationClarification",)


def test_explicit_ambiguity_exposes_meaning_refinement():
    decision_profile = profile()
    ambiguous = context(
        status=CrossCandidateStatus.StableAcrossCandidates,
        ambiguities=(Ambiguity("same", "тот же", "identity ambiguity"),),
    )
    request = build_clarification_request(ambiguous, decision_profile)
    assert request.choices == ("NeedMeaningClarification",)


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
