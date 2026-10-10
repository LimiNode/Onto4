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
from onto4.core.admission import Diagnostic
from onto4.core.values import UnknownReason
from onto4.pipeline import (
    apply_clarification_answer,
    build_clarification_request,
    decide_clarification,
    decide_clarification_question,
    decide_clarification_turn,
)
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
    ClarificationKind,
    ClarificationQuestion,
    ClarificationTurn,
    ClarificationContext,
    ConceptualDepth,
    CrossCandidateStatus,
    FormalizationCandidate,
    FixtureClarificationPolicy,
    InterpretationSpace,
    PipelineDisposition,
    SemanticReading,
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


def comparison_context(status, candidates):
    formalization_candidates = tuple(
        FormalizationCandidate(
            id=identifier,
            label=identifier,
            formalization_id=formalization_id,
            context_id=context_id,
            formalization=PredicateExpr(PredicateCall(identifier, ())),
            reading_id=reading_id,
        )
        for identifier, formalization_id, context_id, reading_id, _ in candidates
    )
    assessments = tuple(
        CandidateAssessment(
            candidate,
            candidate.context_id,
            AssessmentResult(
                state=AssessmentState.Assessed,
                semantic_status=SemanticStatus.Admitted,
                verdict=spec[-1],
                evidence=None,
            ),
        )
        for candidate, spec in zip(formalization_candidates, candidates)
    )
    reading_ids = tuple(
        dict.fromkeys(
            candidate.reading_id
            for candidate in formalization_candidates
            if candidate.reading_id is not None
        )
    )
    interpretation = InterpretationSpace(
        id="comparison",
        source_text="Question",
        conceptual_depth=ConceptualDepth.Philosophical,
        readings=tuple(
            SemanticReading(reading_id, reading_id, reading_id)
            for reading_id in reading_ids
        ),
    )
    return ClarificationContext(
        interpretation=interpretation,
        candidates=formalization_candidates,
        assessments=assessments,
        landscape=AssessmentLandscape(assessments=assessments, status=status),
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


def test_formalization_conflict_with_discriminating_readings_exposes_meaning_only():
    decision_profile = profile()
    reading_context = comparison_context(
        CrossCandidateStatus.FormalizationConflict,
        (
            ("first", "formal-a", "context", "reading-a", Verdict.T),
            ("second", "formal-b", "context", "reading-b", Verdict.F),
        ),
    )
    request = build_clarification_request(reading_context, decision_profile)

    assert request.choices == ("NeedMeaningClarification",)


@pytest.mark.parametrize(
    "status",
    (
        CrossCandidateStatus.FormalizationConflict,
        CrossCandidateStatus.MixedDependence,
    ),
)
def test_shared_reading_does_not_misattribute_formalization_conflict_to_meaning(
    status,
):
    decision_profile = profile()
    shared_reading = comparison_context(
        status,
        (
            ("first", "formal-a", "context-a", "continuity", Verdict.T),
            ("second", "formal-b", "context-b", "continuity", Verdict.F),
        ),
    )

    request = build_clarification_request(shared_reading, decision_profile)
    question = FixtureClarificationPolicy().choose(shared_reading)

    assert request.choices == ("NeedFormalizationClarification",)
    assert question.kind is ClarificationKind.Formalization
    assert question.choices == ("first", "second")


@pytest.mark.parametrize(
    "status",
    (
        CrossCandidateStatus.FormalizationConflict,
        CrossCandidateStatus.MixedDependence,
    ),
)
def test_one_to_one_readings_discriminate_competing_formalizations(status):
    decision_profile = profile()
    discriminated = comparison_context(
        status,
        (
            ("first", "formal-a", "context-a", "continuity", Verdict.T),
            ("second", "formal-b", "context-b", "substance", Verdict.F),
        ),
    )

    request = build_clarification_request(discriminated, decision_profile)
    question = FixtureClarificationPolicy().choose(discriminated)

    assert request.choices == ("NeedMeaningClarification",)
    assert question.kind is ClarificationKind.Meaning
    assert question.choices == ("continuity", "substance")


@pytest.mark.parametrize(
    "status",
    (
        CrossCandidateStatus.FormalizationConflict,
        CrossCandidateStatus.MixedDependence,
    ),
)
def test_partially_collapsed_readings_stay_formalization_clarification(status):
    decision_profile = profile()
    collapsed = comparison_context(
        status,
        (
            ("first", "formal-a", "context-a", "reading-1", Verdict.T),
            ("second", "formal-b", "context-b", "reading-1", Verdict.F),
            ("third", "formal-c", "context-c", "reading-2", Verdict.T),
        ),
    )

    request = build_clarification_request(collapsed, decision_profile)
    question = FixtureClarificationPolicy().choose(collapsed)

    assert request.choices == ("NeedFormalizationClarification",)
    assert question.kind is ClarificationKind.Formalization
    assert len(question.choices) == 3


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


def test_provider_selects_question_kind_within_provenance_bound_options():
    decision_profile = profile()
    unresolved = context(
        status=CrossCandidateStatus.FormalizationUnresolved,
        result=AssessmentResult(
            state=AssessmentState.FormalizationUnresolved,
            semantic_status=None,
            verdict=None,
            evidence=None,
            diagnostics=(
                Diagnostic("unknown_symbol", "missing symbol"),
                Diagnostic("unknown_predicate", "missing predicate"),
            ),
        ),
        unresolved_candidate_ids=("candidate",),
    )
    request = build_clarification_request(unresolved, decision_profile)
    assert request.choices == (
        "NeedReferenceClarification",
        "NeedMeaningClarification",
    )
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "NeedMeaningClarification")},
    )

    result = decide_clarification_question(
        unresolved,
        profile=decision_profile,
        provider=provider,
        clarification_policy=FixtureClarificationPolicy(),
    )

    assert result.question is not None
    assert result.question.kind is ClarificationKind.Meaning
    assert result.question.target_ids == ("candidate",)
    assert result.decision_result.disposition is PipelineDisposition.AskClarification


def test_question_bridge_preserves_abstention_without_fallback_question():
    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, abstained=True)},
    )

    result = decide_clarification_question(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=FixtureClarificationPolicy(),
    )

    assert result.question is None
    assert result.decision_result.selected_choice is None
    assert result.decision_result.disposition is None


def test_question_bridge_fails_closed_when_policy_cannot_realize_kind():
    class EmptyQuestionPolicy:
        def choose(self, context):
            return None

        def choose_for_kind(self, context, kind):
            return None

    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )

    with pytest.raises(ValueError, match="cannot produce"):
        decide_clarification_question(
            clarification_context,
            profile=decision_profile,
            provider=provider,
            clarification_policy=EmptyQuestionPolicy(),
        )


def test_question_bridge_rejects_policy_kind_mismatch():
    class WrongKindPolicy:
        def choose(self, context):
            return None

        def choose_for_kind(self, context, kind):
            return ClarificationQuestion(
                id="wrong-kind",
                kind=ClarificationKind.Formalization,
                text="wrong kind",
                target_ids=("candidate",),
            )

    decision_profile = profile()
    ambiguous = context(
        status=CrossCandidateStatus.StableAcrossCandidates,
        ambiguities=(Ambiguity("same", "тот же", "identity ambiguity"),),
    )
    request = build_clarification_request(ambiguous, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, "NeedMeaningClarification")},
    )

    with pytest.raises(ValueError, match="cannot produce"):
        decide_clarification_question(
            ambiguous,
            profile=decision_profile,
            provider=provider,
            clarification_policy=WrongKindPolicy(),
        )


def test_clarification_turn_can_remain_pending_without_transition():
    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )

    result = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=FixtureClarificationPolicy(),
    )

    assert result.decision.question is not None
    assert result.pending is not None
    assert result.pending.interpretation_id == "interpretation"
    assert result.pending.decision is result.decision
    assert result.successor is None
    assert result.turn is None


def test_clarification_turn_records_answer_and_successor_snapshot():
    decision_profile = profile()
    clarification_context = context()
    question = FixtureClarificationPolicy().choose(clarification_context)
    successor = InterpretationSpace(
        id="successor",
        source_text="Question clarified",
        conceptual_depth=ConceptualDepth.Philosophical,
    )
    clarification_policy = FixtureClarificationPolicy(
        transitions={
            (
                clarification_context.interpretation.id,
                question.id,
                "candidate",
            ): successor
        }
    )
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )

    issued = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=clarification_policy,
    )
    result = apply_clarification_answer(
        clarification_context,
        pending=issued.pending,
        clarification_policy=clarification_policy,
        answer="candidate",
    )

    assert result.successor is successor
    assert result.turn.previous_interpretation_id == "interpretation"
    assert result.turn.question_id == question.id
    assert result.turn.answer == "candidate"
    assert result.turn.successor_interpretation_id == "successor"
    assert result.pending is issued.pending


def test_clarification_turn_rejects_answer_outside_question_choices():
    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )

    issued = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=FixtureClarificationPolicy(),
    )

    with pytest.raises(ValueError, match="not one of"):
        apply_clarification_answer(
            clarification_context,
            pending=issued.pending,
            clarification_policy=FixtureClarificationPolicy(),
            answer="unavailable-candidate",
        )


def test_provider_abstention_produces_no_pending_clarification():
    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, abstained=True)},
    )

    result = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=FixtureClarificationPolicy(),
    )

    assert result.decision.question is None
    assert result.pending is None
    assert result.successor is None
    assert result.turn is None


def test_answer_submission_requires_previously_issued_pending_question():
    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )

    with pytest.raises(ValueError, match="requires the PendingClarification"):
        decide_clarification_turn(
            clarification_context,
            profile=decision_profile,
            provider=provider,
            clarification_policy=FixtureClarificationPolicy(),
            answer="candidate",
        )


def test_clarification_turn_rejects_inconsistent_transition_provenance():
    clarification_context = context()
    successor = InterpretationSpace(
        id="successor",
        source_text="Question clarified",
        conceptual_depth=ConceptualDepth.Philosophical,
    )

    class InconsistentTransitionPolicy:
        def choose(self, supplied_context):
            return FixtureClarificationPolicy().choose(supplied_context)

        def choose_for_kind(self, supplied_context, kind):
            return FixtureClarificationPolicy().choose_for_kind(
                supplied_context, kind
            )

        def successor(self, *, interpretation, question, answer):
            return successor, ClarificationTurn(
                previous_interpretation_id="unrelated",
                question_id=question.id,
                answer=answer,
                successor_interpretation_id=successor.id,
            )

    decision_profile = profile()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )

    issued = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=InconsistentTransitionPolicy(),
    )

    with pytest.raises(ValueError, match="inconsistent turn provenance"):
        apply_clarification_answer(
            clarification_context,
            pending=issued.pending,
            clarification_policy=InconsistentTransitionPolicy(),
            answer="candidate",
        )


def test_answering_pending_question_does_not_invoke_provider_again():
    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)

    class MutableProvider:
        calls = 0
        next_decision = decision(
            decision_profile, "NeedFormalizationClarification"
        )

        def decide(self, supplied_request):
            self.calls += 1
            assert supplied_request.question == request.question
            return self.next_decision

    provider = MutableProvider()
    question = FixtureClarificationPolicy().choose(clarification_context)
    successor = InterpretationSpace(
        id="successor",
        source_text="Question clarified",
        conceptual_depth=ConceptualDepth.Philosophical,
    )
    policy = FixtureClarificationPolicy(
        transitions={
            ("interpretation", question.id, "candidate"): successor,
        }
    )
    issued = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=policy,
    )
    provider.next_decision = decision(
        decision_profile, "NeedReferenceClarification"
    )

    result = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=policy,
        pending=issued.pending,
        answer="candidate",
    )

    assert provider.calls == 1
    assert result.decision.question.id == question.id
    assert result.successor is successor
    assert not hasattr(result, "assessments")


def test_pending_question_from_another_interpretation_is_rejected():
    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )
    issued = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=FixtureClarificationPolicy(),
    )
    other_context = replace(
        clarification_context,
        interpretation=replace(
            clarification_context.interpretation,
            id="other-interpretation",
        ),
    )

    with pytest.raises(ValueError, match="different interpretation"):
        apply_clarification_answer(
            other_context,
            pending=issued.pending,
            clarification_policy=FixtureClarificationPolicy(),
            answer="candidate",
        )


@pytest.mark.parametrize(
    "tampered_question",
    (
        lambda question: replace(question, id="tampered-id"),
        lambda question: replace(question, kind=ClarificationKind.Reference),
    ),
)
def test_tampered_pending_question_identity_is_rejected(tampered_question):
    decision_profile = profile()
    clarification_context = context()
    request = build_clarification_request(clarification_context, decision_profile)
    provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: decision(
                decision_profile, "NeedFormalizationClarification"
            )
        },
    )
    issued = decide_clarification_turn(
        clarification_context,
        profile=decision_profile,
        provider=provider,
        clarification_policy=FixtureClarificationPolicy(),
    )
    tampered_decision = replace(
        issued.pending.decision,
        question=tampered_question(issued.pending.decision.question),
    )
    tampered_pending = replace(issued.pending, decision=tampered_decision)

    with pytest.raises(ValueError, match="question (id|kind) provenance"):
        apply_clarification_answer(
            clarification_context,
            pending=tampered_pending,
            clarification_policy=FixtureClarificationPolicy(),
            answer="candidate",
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
