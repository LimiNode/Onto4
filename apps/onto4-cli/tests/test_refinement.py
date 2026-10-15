from dataclasses import replace

import pytest

from onto4.pipeline import (
    RefinementCommitLedger,
    RefinementDelta,
    RefinementEffect,
    RefinementOperation,
    RefinementRequest,
    RefinementValidationError,
    apply_refinement_batch,
    apply_refinement_delta,
)
from onto4.reasoning import (
    Ambiguity,
    ConceptualDepth,
    InterpretationSpace,
    OntologyCandidate,
    Presupposition,
    SemanticReading,
)


def _space(identifier="initial"):
    return InterpretationSpace(
        id=identifier,
        source_text="The claim",
        conceptual_depth=ConceptualDepth.Ordinary,
        ambiguities=(Ambiguity("ambiguity-0", "term", "two meanings"),),
        presuppositions=(Presupposition("presupposition-0", "an entity exists"),),
        ontologies=(OntologyCandidate("ontology-0", "ordinary", "ordinary objects"),),
        readings=(
            SemanticReading("reading-0", "first", "first reading"),
            SemanticReading("reading-1", "second", "second reading"),
        ),
    )


def _request(space=None):
    space = space or _space()
    return RefinementRequest(
        interpretation=space,
        assessment_interpretation_id=space.id,
        allowed_reading_ids=frozenset(item.id for item in space.readings),
        allowed_ambiguity_ids=frozenset(item.id for item in space.ambiguities),
        allowed_ontology_ids=frozenset(item.id for item in space.ontologies),
        allowed_presupposition_ids=frozenset(item.id for item in space.presuppositions),
    )


def test_select_reading_is_host_bound_and_preserves_source_and_depth():
    request = _request()
    result = apply_refinement_delta(
        request,
        RefinementDelta(
            RefinementOperation.SELECT_READING,
            target_id="reading-1",
            resolved_ambiguity_ids=("ambiguity-0",),
        ),
        successor_id="successor",
    )

    assert result.successor.source_text == request.interpretation.source_text
    assert result.successor.conceptual_depth is request.interpretation.conceptual_depth
    assert result.successor.readings[0].id == "reading-1"
    assert result.successor.ambiguities == ()
    assert result.commitment.effect is RefinementEffect.APPLIED


def test_refine_ambiguity_preserves_host_id_and_requires_target():
    request = _request()
    result = apply_refinement_delta(
        request,
        RefinementDelta(
            RefinementOperation.REFINE_AMBIGUITY,
            target_id="ambiguity-0",
            text="term",
            description="one explicit meaning",
        ),
        successor_id="successor",
    )

    assert result.successor.ambiguities[0].id == "ambiguity-0"
    assert result.successor.ambiguities[0].description == "one explicit meaning"

    with pytest.raises(RefinementValidationError, match="Unknown or inadmissible"):
        apply_refinement_delta(
            request,
            RefinementDelta(
                RefinementOperation.REFINE_AMBIGUITY,
                target_id="missing",
                text="term",
                description="meaning",
            ),
            successor_id="successor",
        )


def test_add_presupposition_assigns_id_and_does_not_accept_model_id():
    request = _request()
    result = apply_refinement_delta(
        request,
        RefinementDelta(
            RefinementOperation.ADD_PRESUPPOSITION,
            description="the speaker commits to an identity bearer",
        ),
        successor_id="successor",
    )

    assert result.successor.presuppositions[-1].id == "presupposition-1"
    with pytest.raises(RefinementValidationError, match="unknown fields"):
        RefinementDelta.from_mapping(
            {
                "operation": "add_presupposition",
                "description": "meaning",
                "id": "model-invented",
            }
        )


def test_stale_assessment_and_stale_target_are_rejected():
    space = _space()
    with pytest.raises(RefinementValidationError, match="assessment snapshot"):
        RefinementRequest(
            interpretation=space,
            assessment_interpretation_id="other-snapshot",
        )

    request = _request(space)
    stale = replace(space, id="successor")
    stale_request = replace(request, interpretation=stale, assessment_interpretation_id=stale.id)
    with pytest.raises(RefinementValidationError, match="Unknown or inadmissible"):
        apply_refinement_delta(
            stale_request,
            RefinementDelta(RefinementOperation.SELECT_READING, target_id="missing"),
            successor_id="next",
        )

    with pytest.raises(RefinementValidationError, match="absent from the snapshot"):
        replace(request, allowed_reading_ids=frozenset({"reading-missing"}))


def test_abstention_preserves_snapshot_without_inventing_commitment():
    request = _request()
    result = apply_refinement_delta(
        request,
        RefinementDelta(RefinementOperation.ABSTAIN),
        successor_id="ignored",
    )

    assert result.successor is request.interpretation
    assert result.commitment.effect is RefinementEffect.ABSTAINED
    assert result.commitment.successor_interpretation_id == request.interpretation.id


def test_retain_ambiguity_is_explicit_no_effect_and_cannot_advance_snapshot():
    request = _request()
    result = apply_refinement_delta(
        request,
        RefinementDelta(RefinementOperation.RETAIN_AMBIGUITY, target_id="ambiguity-0"),
        successor_id="successor",
    )

    assert result.successor is request.interpretation
    assert result.commitment.effect is RefinementEffect.NO_EFFECT
    with pytest.raises(RefinementValidationError, match="no-effect"):
        apply_refinement_batch(
            request,
            (RefinementDelta(RefinementOperation.RETAIN_AMBIGUITY, target_id="ambiguity-0"),),
            successor_id="successor",
        )


def test_conflicting_batch_and_failed_admission_leave_original_snapshot_and_ledger():
    request = _request()
    original = request.interpretation
    with pytest.raises(RefinementValidationError, match="Conflicting"):
        apply_refinement_batch(
            request,
            (
                RefinementDelta(
                    RefinementOperation.REFINE_AMBIGUITY,
                    target_id="ambiguity-0",
                    text="term",
                    description="first",
                ),
                RefinementDelta(
                    RefinementOperation.REFINE_AMBIGUITY,
                    target_id="ambiguity-0",
                    text="term",
                    description="second",
                ),
            ),
            successor_id="successor",
        )
    ledger = RefinementCommitLedger()
    assert original is request.interpretation
    commitment = apply_refinement_delta(
        request,
        RefinementDelta(RefinementOperation.ADD_PRESUPPOSITION, description="new"),
        successor_id="successor",
    ).commitment
    ledger = ledger.record(commitment)
    with pytest.raises(RefinementValidationError, match="already recorded"):
        ledger.record(commitment)
    assert len(ledger.commitments) == 1


def test_batch_applies_multiple_nonconflicting_operations_atomically():
    request = _request()
    result = apply_refinement_batch(
        request,
        (
            RefinementDelta(
                RefinementOperation.REFINE_AMBIGUITY,
                target_id="ambiguity-0",
                text="term",
                description="refined meaning",
            ),
            RefinementDelta(
                RefinementOperation.ADD_PRESUPPOSITION,
                description="identity bearer",
            ),
        ),
        successor_id="successor",
    )

    assert result.successor.id == "successor"
    assert result.successor.ambiguities[0].description == "refined meaning"
    assert len(result.successor.presuppositions) == 2
    assert result.source_interpretation_id == request.interpretation.id
    assert len(result.commitments) == 2
    assert [item.operation for item in result.commitments] == [
        RefinementOperation.REFINE_AMBIGUITY,
        RefinementOperation.ADD_PRESUPPOSITION,
    ]


@pytest.mark.parametrize(
    "delta",
    (
        RefinementDelta(
            RefinementOperation.REFINE_AMBIGUITY,
            target_id="ambiguity-0",
            text="term",
            description="two meanings",
        ),
        RefinementDelta(
            RefinementOperation.QUALIFY_ONTOLOGY_CANDIDATE,
            target_id="ontology-0",
            description="ordinary objects",
        ),
    ),
)
def test_new_snapshot_id_alone_is_no_effect(delta):
    request = _request()
    result = apply_refinement_delta(request, delta, successor_id="new-id")

    assert result.successor is request.interpretation
    assert result.commitment.effect is RefinementEffect.NO_EFFECT


def test_changed_content_requires_distinct_successor_id():
    request = _request()
    with pytest.raises(RefinementValidationError, match="distinct successor_id"):
        apply_refinement_delta(
            request,
            RefinementDelta(
                RefinementOperation.REFINE_AMBIGUITY,
                target_id="ambiguity-0",
                text="term",
                description="one meaning",
            ),
            successor_id=request.interpretation.id,
        )


def test_select_reading_removes_only_declared_resolved_ambiguities():
    space = replace(
        _space(),
        ambiguities=(
            Ambiguity("ambiguity-0", "determines", "cause or essence"),
            Ambiguity("ambiguity-1", "personality", "traits or identity"),
        ),
    )
    request = _request(space)
    result = apply_refinement_delta(
        request,
        RefinementDelta(
            RefinementOperation.SELECT_READING,
            target_id="reading-1",
            resolved_ambiguity_ids=("ambiguity-0",),
        ),
        successor_id="successor",
    )

    assert tuple(item.id for item in result.successor.ambiguities) == ("ambiguity-1",)


def test_operation_specific_schema_rejects_ignored_fields():
    with pytest.raises(RefinementValidationError, match="does not accept"):
        RefinementDelta(
            RefinementOperation.SELECT_READING,
            target_id="reading-0",
            description="silently ignored before the fix",
        )


def test_batch_failure_does_not_publish_partial_commitments():
    request = _request()
    with pytest.raises(RefinementValidationError, match="Unknown or inadmissible"):
        apply_refinement_batch(
            request,
            (
                RefinementDelta(
                    RefinementOperation.ADD_PRESUPPOSITION,
                    description="valid first operation",
                ),
                RefinementDelta(
                    RefinementOperation.REFINE_AMBIGUITY,
                    target_id="missing",
                    text="term",
                    description="invalid second operation",
                ),
            ),
            successor_id="successor",
            batch_id="batch-0",
        )

    assert request.interpretation == _space()
