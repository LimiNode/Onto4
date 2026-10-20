import pytest

from onto4.pipeline import (
    AdjudicationDecision,
    BasisSchemaError,
    BindingRelation,
    CheckStatus,
    CommitmentState,
    GENOME_IDENTITY_BASIS,
    INTRINSIC_TIME_BASIS,
    ProfileAdjudicationEvidence,
    ProfileRelativeAdjudicationBasis,
    evaluate_profile_basis,
    parse_profile_evidence,
)


def _genome(**overrides):
    commitments = {
        "identity_criterion_is_numerical": "affirmed",
        "shared_genome_is_not_sufficient": "affirmed",
        "distinct_persons_can_share_genome": "affirmed",
    }
    commitments.update(overrides.pop("commitments", {}))
    payload = {
        "case_id": "genome-identity-bounded",
        "target_id": "ambiguity-genome",
        "relation": "anchored_update",
        "commitments": commitments,
    }
    payload.update(overrides)
    return payload


def _time(**overrides):
    commitments = {
        "present_is_observer_independent": "affirmed",
        "sequence_order_alone_is_not_the_present": "affirmed",
    }
    commitments.update(overrides.pop("commitments", {}))
    payload = {
        "case_id": "intrinsic-time-bounded",
        "target_id": "ambiguity-present",
        "relation": "anchored_update",
        "commitments": commitments,
    }
    payload.update(overrides)
    return payload


def test_genome_profile_can_verify_all_declared_commitments():
    result = evaluate_profile_basis(_genome(), basis=GENOME_IDENTITY_BASIS)
    assert result.schema is CheckStatus.VALID
    assert result.comparability is CheckStatus.VALID
    assert result.decision is AdjudicationDecision.VERIFIED
    assert result.missing_commitments == ()
    assert result.contradictory_commitments == ()


def test_genome_profile_contradicts_genetic_essentialism():
    result = evaluate_profile_basis(
        _genome(commitments={"shared_genome_is_not_sufficient": "denied"}),
        basis=GENOME_IDENTITY_BASIS,
    )
    assert result.decision is AdjudicationDecision.CONTRADICTED
    assert result.contradictory_commitments == ("shared_genome_is_not_sufficient",)


def test_genome_profile_is_unverified_when_identity_criterion_is_omitted():
    result = evaluate_profile_basis(
        _genome(commitments={"identity_criterion_is_numerical": "unspecified"}),
        basis=GENOME_IDENTITY_BASIS,
    )
    assert result.decision is AdjudicationDecision.UNVERIFIED
    assert result.missing_commitments == ("identity_criterion_is_numerical",)


def test_intrinsic_time_profile_can_verify_declared_observer_independent_commitment():
    result = evaluate_profile_basis(_time(), basis=INTRINSIC_TIME_BASIS)
    assert result.decision is AdjudicationDecision.VERIFIED


def test_intrinsic_time_profile_contradicts_relational_only_reduction():
    result = evaluate_profile_basis(
        _time(commitments={"present_is_observer_independent": "denied"}),
        basis=INTRINSIC_TIME_BASIS,
    )
    assert result.decision is AdjudicationDecision.CONTRADICTED
    assert result.contradictory_commitments == ("present_is_observer_independent",)


def test_intrinsic_time_profile_is_unverified_when_order_commitment_is_missing():
    result = evaluate_profile_basis(
        _time(commitments={"sequence_order_alone_is_not_the_present": "unspecified"}),
        basis=INTRINSIC_TIME_BASIS,
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
        relation=BindingRelation.ANCHORED_UPDATE,
        commitments={
            "identity_criterion_is_numerical": "affirmed",
            "shared_genome_is_not_sufficient": "affirmed",
            "distinct_persons_can_share_genome": "affirmed",
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


def test_profile_digest_is_canonical_over_criterion_order():
    reordered = ProfileRelativeAdjudicationBasis(
        basis_id=GENOME_IDENTITY_BASIS.basis_id,
        version=GENOME_IDENTITY_BASIS.version,
        case_id=GENOME_IDENTITY_BASIS.case_id,
        target_id=GENOME_IDENTITY_BASIS.target_id,
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
