from onto4.core import (
    AssessmentContext,
    OntologyProfile,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    Verdict,
)
from onto4.core.evidence import AtomicVerdictStore
from onto4.reasoning import (
    Ambiguity,
    ConceptualDepth,
    CrossCandidateStatus,
    FormalizationCandidate,
    InterpretationSpace,
    SemanticReading,
    aggregate_assessments,
    assess_candidates,
)


def atom(name: str) -> PredicateExpr:
    return PredicateExpr(PredicateCall(name, ()))


def context(*, verdicts=None, predicates=("a", "b")) -> AssessmentContext:
    return AssessmentContext(
        ontology=OntologyProfile(
            name="fixture",
            predicates={name: PredicateSignature(()) for name in predicates},
        ),
        verdicts=AtomicVerdictStore(verdicts or {}),
    )


def candidate(identifier, label, formalization_id, context_id, expression, reading_id=None):
    return FormalizationCandidate(
        id=identifier,
        label=label,
        formalization_id=formalization_id,
        context_id=context_id,
        formalization=expression,
        reading_id=reading_id,
    )


def test_interpretation_space_preserves_readings_without_verdicts():
    space = InterpretationSpace(
        id="identity-question",
        source_text="Я тот же человек, которым был в детстве?",
        conceptual_depth=ConceptualDepth.Philosophical,
        ambiguities=(Ambiguity("identity-term", "тот же", "критерий идентичности не задан"),),
        readings=(
            SemanticReading("continuity", "непрерывность", "тождество через continuity"),
            SemanticReading("substance", "субстанция", "численная тождественность сущности"),
        ),
    )

    assert len(space.readings) == 2
    assert not hasattr(space, "verdict")


def test_same_verdict_across_candidates_is_stable():
    candidates = [
        candidate("a", "reading A", "formal-a", "fixture", atom("a")),
        candidate("b", "reading B", "formal-b", "fixture", atom("b")),
    ]
    assessments = assess_candidates(
        candidates,
        {"fixture": context(verdicts={"a()": Verdict.T, "b()": Verdict.T})},
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.StableAcrossCandidates
    assert all(item.result.verdict is Verdict.T for item in landscape.assessments)


def test_different_contexts_produce_context_dependent_landscape():
    candidates = [
        candidate("present", "present reading", "same-formalization", "present", atom("a")),
        candidate("eternal", "eternal reading", "same-formalization", "eternal", atom("a")),
    ]
    assessments = assess_candidates(
        candidates,
        {
            "present": context(verdicts={"a()": Verdict.T}),
            "eternal": context(verdicts={"a()": Verdict.F}),
        },
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.ContextDependent
    assert landscape.varies_by_context is True
    assert landscape.varies_by_formalization is False


def test_stable_verdict_still_records_context_variation():
    candidates = [
        candidate("present", "present reading", "same-formalization", "present", atom("a")),
        candidate("eternal", "eternal reading", "same-formalization", "eternal", atom("a")),
    ]
    assessments = assess_candidates(
        candidates,
        {
            "present": context(verdicts={"a()": Verdict.T}),
            "eternal": context(verdicts={"a()": Verdict.T}),
        },
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.StableAcrossCandidates
    assert landscape.varies_by_context is True
    assert landscape.varies_by_formalization is False


def test_different_formalizations_in_one_context_are_a_conflict():
    candidates = [
        candidate("a", "reading A", "formal-a", "fixture", atom("a")),
        candidate("b", "reading B", "formal-b", "fixture", atom("b")),
    ]
    assessments = assess_candidates(
        candidates,
        {"fixture": context(verdicts={"a()": Verdict.T, "b()": Verdict.F})},
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.FormalizationConflict
    assert landscape.varies_by_context is False
    assert landscape.varies_by_formalization is True


def test_stable_verdict_still_records_formalization_variation():
    candidates = [
        candidate("a", "reading A", "formal-a", "fixture", atom("a")),
        candidate("b", "reading B", "formal-b", "fixture", atom("b")),
    ]
    assessments = assess_candidates(
        candidates,
        {"fixture": context(verdicts={"a()": Verdict.T, "b()": Verdict.T})},
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.StableAcrossCandidates
    assert landscape.varies_by_context is False
    assert landscape.varies_by_formalization is True


def test_unresolved_candidate_keeps_landscape_meta_level():
    candidates = [
        candidate("resolved", "resolved reading", "formal-a", "fixture", atom("a")),
        candidate("pending", "pending reading", "formal-pending", "fixture", None),
    ]
    assessments = assess_candidates(
        candidates,
        {"fixture": context(verdicts={"a()": Verdict.T})},
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.FormalizationUnresolved
    assert landscape.unresolved_candidate_ids == ("pending",)
    assert landscape.assessments[0].result.verdict is Verdict.T
    assert landscape.assessments[1].result.verdict is None


def test_category_error_and_unknown_result_can_be_compared_without_collapsing():
    process = AssessmentContext(
        ontology=OntologyProfile(
            name="process",
            types={"me": "PersonState"},
            predicates={"continuity": PredicateSignature(())},
            absent_concepts={"same_substance"},
        ),
    )
    candidates = [
        candidate("continuity", "continuity", "continuity", "process", PredicateExpr(PredicateCall("continuity", ()))),
        candidate("substance", "substance", "substance", "process", PredicateExpr(PredicateCall("same_substance", ()))),
    ]
    assessments = assess_candidates(candidates, {"process": process})

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.FormalizationConflict
    assert [item.result.verdict for item in landscape.assessments] == [Verdict.U, Verdict.C]


def test_different_formalizations_and_contexts_are_mixed_dependence():
    candidates = [
        candidate("present", "present reading", "present-formal", "present", atom("a")),
        candidate("eternal", "eternal reading", "eternal-formal", "eternal", atom("a")),
    ]
    assessments = assess_candidates(
        candidates,
        {
            "present": context(verdicts={"a()": Verdict.T}),
            "eternal": context(verdicts={"a()": Verdict.F}),
        },
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.MixedDependence
    assert landscape.varies_by_context is True
    assert landscape.varies_by_formalization is True


def test_invalid_candidate_has_distinct_landscape_status():
    candidates = [
        candidate("invalid", "invalid reading", "invalid-formal", "fixture", object()),
    ]
    assessments = assess_candidates(candidates, {"fixture": context()})

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.InvalidRequest
    assert landscape.invalid_candidate_ids == ("invalid",)
    assert landscape.unresolved_candidate_ids == ()


def test_shared_formalization_id_with_different_structures_fails_closed():
    candidates = [
        candidate("first", "first", "shared", "fixture", atom("a")),
        candidate("second", "second", "shared", "fixture", atom("b")),
    ]
    assessments = assess_candidates(
        candidates,
        {"fixture": context(verdicts={"a()": Verdict.T, "b()": Verdict.T})},
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.InvalidRequest
    assert landscape.invalid_candidate_ids == ("first", "second")
    assert landscape.invalid_reasons == ("formalization_id_conflict",)


def test_shared_formalization_id_with_different_assumptions_fails_closed():
    candidates = [
        FormalizationCandidate(
            id="first",
            label="first",
            formalization_id="shared",
            context_id="fixture",
            formalization=atom("a"),
            assumptions=("identity_is_continuous",),
        ),
        FormalizationCandidate(
            id="second",
            label="second",
            formalization_id="shared",
            context_id="fixture",
            formalization=atom("a"),
            assumptions=("identity_is_substantial",),
        ),
    ]
    assessments = assess_candidates(
        candidates,
        {"fixture": context(verdicts={"a()": Verdict.T})},
    )

    landscape = aggregate_assessments(assessments)

    assert landscape.status is CrossCandidateStatus.InvalidRequest
    assert landscape.invalid_candidate_ids == ("first", "second")
    assert landscape.invalid_reasons == ("formalization_id_conflict",)
