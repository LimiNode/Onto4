import pytest

from onto4.pipeline import (
    AdjudicationDecision,
    BasisSchemaError,
    BasisScope,
    BindingRelation,
    CheckStatus,
    CommitmentState,
    GENOME_IDENTITY_BASIS,
    GENOME_IDENTITY_FIRST_TURN_BASIS,
    GENOME_IDENTITY_WHOLE_DIALOGUE_BASIS,
    INTRINSIC_TIME_BASIS,
    INTRINSIC_TIME_FIRST_TURN_BASIS,
    INTRINSIC_TIME_WHOLE_DIALOGUE_BASIS,
    ProfileAdjudicationEvidence,
    ProfileRelativeAdjudicationBasis,
    evaluate_profile_basis,
    parse_profile_evidence,
)


def _genome(**overrides):
    commitments = {
        "identity_criterion_is_numerical": "affirmed",
    }
    commitments.update(overrides.pop("commitments", {}))
    payload = {
        "case_id": "genome-identity-bounded",
        "target_id": "ambiguity-genome",
        "question_id": "meaning:ambiguity-genome",
        "answer_ids": ["genome-2"],
        "relation": "anchored_update",
        "commitments": commitments,
    }
    payload.update(overrides)
    return payload


def _time(**overrides):
    commitments = {
        "present_is_observer_independent": "affirmed",
    }
    commitments.update(overrides.pop("commitments", {}))
    payload = {
        "case_id": "intrinsic-time-bounded",
        "target_id": "ambiguity-present",
        "question_id": "meaning:ambiguity-present",
        "answer_ids": ["time-2"],
        "relation": "anchored_update",
        "commitments": commitments,
    }
    payload.update(overrides)
    return payload


def _genome_whole(**overrides):
    payload = {
        "case_id": "genome-identity-bounded",
        "target_id": "ambiguity-criterion",
        "question_id": "meaning:ambiguity-criterion",
        "answer_ids": ["genome-2", "genome-4"],
        "relation": "create",
        "commitments": {
            "shared_genome_is_not_sufficient": "affirmed",
            "distinct_persons_can_share_genome": "affirmed",
        },
    }
    payload.update(overrides)
    return payload


def _time_whole(**overrides):
    payload = {
        "case_id": "intrinsic-time-bounded",
        "target_id": "ambiguity-observer",
        "question_id": "ontology:ambiguity-observer",
        "answer_ids": ["time-2", "time-4"],
        "relation": "anchored_update",
        "commitments": {
            "present_is_observer_independent": "affirmed",
            "sequence_order_alone_is_not_the_present": "affirmed",
        },
    }
    payload.update(overrides)
    return payload


def test_genome_first_turn_profile_verifies_only_first_turn_commitment():
    result = evaluate_profile_basis(_genome(), basis=GENOME_IDENTITY_BASIS)
    assert result.schema is CheckStatus.VALID
    assert result.comparability is CheckStatus.VALID
    assert result.decision is AdjudicationDecision.VERIFIED
    assert result.missing_commitments == ()
    assert result.contradictory_commitments == ()


def test_genome_whole_dialogue_profile_verifies_second_target_commitments():
    result = evaluate_profile_basis(
        _genome_whole(), basis=GENOME_IDENTITY_WHOLE_DIALOGUE_BASIS
    )
    assert result.decision is AdjudicationDecision.VERIFIED


def test_genome_first_turn_profile_contradicts_numerical_identity_reversal():
    result = evaluate_profile_basis(
        _genome(commitments={"identity_criterion_is_numerical": "denied"}),
        basis=GENOME_IDENTITY_BASIS,
    )
    assert result.decision is AdjudicationDecision.CONTRADICTED
    assert result.contradictory_commitments == ("identity_criterion_is_numerical",)


def test_genome_whole_dialogue_profile_contradicts_genetic_essentialism():
    result = evaluate_profile_basis(
        _genome_whole(commitments={"shared_genome_is_not_sufficient": "denied"}),
        basis=GENOME_IDENTITY_WHOLE_DIALOGUE_BASIS,
    )
    assert result.decision is AdjudicationDecision.CONTRADICTED
    assert result.contradictory_commitments == ("shared_genome_is_not_sufficient",)


def test_genome_first_turn_profile_is_unverified_when_identity_criterion_is_omitted():
    result = evaluate_profile_basis(
        _genome(commitments={"identity_criterion_is_numerical": "unspecified"}),
        basis=GENOME_IDENTITY_BASIS,
    )
    assert result.decision is AdjudicationDecision.UNVERIFIED
    assert result.missing_commitments == ("identity_criterion_is_numerical",)


def test_genome_whole_dialogue_profile_is_unverified_when_second_answer_is_missing():
    result = evaluate_profile_basis(
        _genome_whole(
            commitments={
                "shared_genome_is_not_sufficient": "affirmed",
                "distinct_persons_can_share_genome": "unspecified",
            }
        ),
        basis=GENOME_IDENTITY_WHOLE_DIALOGUE_BASIS,
    )
    assert result.decision is AdjudicationDecision.UNVERIFIED
    assert result.missing_commitments == ("distinct_persons_can_share_genome",)


def test_intrinsic_time_first_turn_profile_verifies_declared_commitment():
    result = evaluate_profile_basis(_time(), basis=INTRINSIC_TIME_BASIS)
    assert result.decision is AdjudicationDecision.VERIFIED


def test_intrinsic_time_whole_dialogue_profile_verifies_second_target_commitments():
    result = evaluate_profile_basis(
        _time_whole(), basis=INTRINSIC_TIME_WHOLE_DIALOGUE_BASIS
    )
    assert result.decision is AdjudicationDecision.VERIFIED


def test_intrinsic_time_first_turn_profile_contradicts_observer_dependence():
    result = evaluate_profile_basis(
        _time(commitments={"present_is_observer_independent": "denied"}),
        basis=INTRINSIC_TIME_BASIS,
    )
    assert result.decision is AdjudicationDecision.CONTRADICTED
    assert result.contradictory_commitments == ("present_is_observer_independent",)


def test_intrinsic_time_whole_dialogue_profile_contradicts_order_only_reduction():
    result = evaluate_profile_basis(
        _time_whole(commitments={"sequence_order_alone_is_not_the_present": "denied"}),
        basis=INTRINSIC_TIME_WHOLE_DIALOGUE_BASIS,
    )
    assert result.decision is AdjudicationDecision.CONTRADICTED
    assert result.contradictory_commitments == ("sequence_order_alone_is_not_the_present",)


def test_intrinsic_time_whole_dialogue_profile_is_unverified_when_second_answer_is_missing():
    result = evaluate_profile_basis(
        _time_whole(
            commitments={
                "present_is_observer_independent": "affirmed",
                "sequence_order_alone_is_not_the_present": "unspecified",
            }
        ),
        basis=INTRINSIC_TIME_WHOLE_DIALOGUE_BASIS,
    )
    assert result.decision is AdjudicationDecision.UNVERIFIED
    assert result.missing_commitments == ("sequence_order_alone_is_not_the_present",)


@pytest.mark.parametrize(
    "overrides",
    [
        {"case_id": "intrinsic-time-bounded"},
        {"target_id": "ambiguity-criterion"},
        {"relation": "preserve"},
    ],
)
def test_evidence_for_another_profile_is_not_comparable(overrides):
    result = evaluate_profile_basis(_genome(**overrides), basis=GENOME_IDENTITY_BASIS)
    assert result.schema is CheckStatus.VALID
    assert result.comparability is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_first_turn_profile_rejects_future_answer_ids():
    result = evaluate_profile_basis(
        _genome(answer_ids=["genome-2", "genome-4"]), basis=GENOME_IDENTITY_BASIS
    )
    assert result.comparability is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_missing_evidence_is_not_comparable():
    result = evaluate_profile_basis(None, basis=GENOME_IDENTITY_BASIS)
    assert result.schema is CheckStatus.NOT_APPLICABLE
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_unknown_commitment_is_rejected_fail_closed():
    result = evaluate_profile_basis(
        _genome(commitments={"provider_confidence": "affirmed"}),
        basis=GENOME_IDENTITY_BASIS,
    )
    assert result.schema is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_untyped_commitment_is_rejected_even_when_key_is_known():
    evidence = ProfileAdjudicationEvidence(
        case_id="genome-identity-bounded",
        target_id="ambiguity-genome",
        question_id="meaning:ambiguity-genome",
        answer_ids=("genome-2",),
        relation=BindingRelation.ANCHORED_UPDATE,
        commitments={
            "identity_criterion_is_numerical": "affirmed",
        },
    )
    result = evaluate_profile_basis(evidence, basis=GENOME_IDENTITY_BASIS)
    assert result.schema is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_public_parser_requires_exact_envelope():
    with pytest.raises(BasisSchemaError, match="Unknown profile evidence fields"):
        parse_profile_evidence({**_genome(), "provider_prompt": "private"})
    with pytest.raises(BasisSchemaError, match="Missing profile evidence fields"):
        parse_profile_evidence({key: value for key, value in _time().items() if key != "commitments"})


def test_parser_rejects_unknown_commitment_state():
    with pytest.raises(BasisSchemaError, match="Unsupported commitment state"):
        parse_profile_evidence(_genome(commitments={"shared_genome_is_not_sufficient": "maybe"}))


def test_profile_digest_is_stable_and_case_specific():
    assert len(GENOME_IDENTITY_BASIS.digest) == 64
    assert len(INTRINSIC_TIME_BASIS.digest) == 64
    assert GENOME_IDENTITY_BASIS.digest != INTRINSIC_TIME_BASIS.digest
    assert GENOME_IDENTITY_BASIS.digest == GENOME_IDENTITY_BASIS.digest
    assert GENOME_IDENTITY_BASIS.basis_digest == GENOME_IDENTITY_BASIS.digest
    assert GENOME_IDENTITY_FIRST_TURN_BASIS.scope is BasisScope.FIRST_TURN
    assert INTRINSIC_TIME_FIRST_TURN_BASIS.scope is BasisScope.FIRST_TURN


def test_frozen_profile_digests_are_golden():
    assert GENOME_IDENTITY_FIRST_TURN_BASIS.basis_digest == (
        "de31ba185b941ea7dedb882e35b5762a38f57af549f936544be86639be1b16ba"
    )
    assert GENOME_IDENTITY_WHOLE_DIALOGUE_BASIS.basis_digest == (
        "067d02c47659db18e3a77f723468b41e053e8cbb8d31d46fef813102b080c27b"
    )
    assert INTRINSIC_TIME_FIRST_TURN_BASIS.basis_digest == (
        "fc33a7b897e70d22c2583f9a1a0ae10347956d87346c4876c3f39bf0b3790ce7"
    )
    assert INTRINSIC_TIME_WHOLE_DIALOGUE_BASIS.basis_digest == (
        "bc7ef8d065febf34a8a864f6770e3e58b1e93263bae744476505ecb6e5537890"
    )


def test_profile_digest_is_canonical_over_criterion_order():
    reordered = ProfileRelativeAdjudicationBasis(
        basis_id=GENOME_IDENTITY_BASIS.basis_id,
        version=GENOME_IDENTITY_BASIS.version,
        case_id=GENOME_IDENTITY_BASIS.case_id,
        target_id=GENOME_IDENTITY_BASIS.target_id,
        question_id=GENOME_IDENTITY_BASIS.question_id,
        scope=GENOME_IDENTITY_BASIS.scope,
        available_answer_ids=GENOME_IDENTITY_BASIS.available_answer_ids,
        relation=GENOME_IDENTITY_BASIS.relation,
        criteria=tuple(reversed(GENOME_IDENTITY_BASIS.criteria)),
    )
    assert reordered.basis_digest == GENOME_IDENTITY_BASIS.basis_digest


def test_mapping_input_is_normalized_before_evaluation():
    parsed = parse_profile_evidence(_genome())
    assert parsed.relation is BindingRelation.ANCHORED_UPDATE
    assert parsed.commitments["identity_criterion_is_numerical"] is CommitmentState.AFFIRMED
    result = evaluate_profile_basis(parsed, basis=GENOME_IDENTITY_BASIS)
    assert result.decision is AdjudicationDecision.VERIFIED


def test_typed_evidence_with_mixed_commitment_key_types_fails_closed():
    evidence = ProfileAdjudicationEvidence(
        case_id="genome-identity-bounded",
        target_id="ambiguity-genome",
        question_id="meaning:ambiguity-genome",
        answer_ids=("genome-2",),
        relation=BindingRelation.ANCHORED_UPDATE,
        commitments={1: CommitmentState.AFFIRMED, "identity_criterion_is_numerical": CommitmentState.AFFIRMED},
    )
    result = evaluate_profile_basis(evidence, basis=GENOME_IDENTITY_BASIS)
    assert result.schema is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
