from dataclasses import replace

import pytest

from onto4.pipeline import (
    AdjudicationDecision,
    AdjudicationSchemaError,
    BindingTransition,
    CheckStatus,
    PublicSemanticTarget,
    SemanticTargetCatalog,
    evaluate_binding_claim,
    evaluate_semantic_adjudication,
    parse_adjudication_receipt,
)
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    InterpretationSpace,
)


BASIS_DIGEST = "a" * 64
TRUSTED_REGISTRY = {"human-panel-1": "rubric-v1"}


def _transition() -> BindingTransition:
    previous = InterpretationSpace(
        "snapshot-0",
        "A claim.",
        ConceptualDepth.Philosophical,
        ambiguities=(Ambiguity("a0", "identity", "old", target_id="target-a"),),
    )
    current = replace(
        previous,
        id="snapshot-1",
        ambiguities=(Ambiguity("a1", "identity", "new", target_id="target-a"),),
    )
    question = ClarificationQuestion(
        id="question-0",
        kind=ClarificationKind.Meaning,
        text="Clarify the meaning.",
        target_ids=("target-a",),
    )
    return BindingTransition(previous, current, question)


def _catalog() -> SemanticTargetCatalog:
    return SemanticTargetCatalog(
        1,
        {"target-a": PublicSemanticTarget("target-a", "Meaning", "identity")},
    )


def _binding() -> tuple[BindingTransition, object]:
    transition = _transition()
    binding = evaluate_binding_claim(
        {
            "relation": "anchored_update",
            "target_id": "target-a",
            "target_kind": "Meaning",
            "source_target_id": "target-a",
            "previous_snapshot_id": "snapshot-0",
            "current_snapshot_id": "snapshot-1",
        },
        transition=transition,
        catalog=_catalog(),
    )
    assert binding.structurally_admissible
    return transition, binding


def _receipt(**overrides):
    payload = {
        "previous_snapshot_id": "snapshot-0",
        "current_snapshot_id": "snapshot-1",
        "target_id": "target-a",
        "relation": "anchored_update",
        "decision": "verified",
        "adjudicator_id": "human-panel-1",
        "adjudicator_version": "rubric-v1",
        "basis_digest": BASIS_DIGEST,
    }
    payload.update(overrides)
    return payload


def test_independent_verified_receipt_is_admitted_without_provider_authority():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.schema is CheckStatus.VALID
    assert result.provenance is CheckStatus.VALID
    assert result.origin is CheckStatus.VALID
    assert result.independence is CheckStatus.VALID
    assert result.decision is AdjudicationDecision.VERIFIED
    assert result.verified


def test_contradicted_receipt_remains_explicitly_contradicted():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(decision="contradicted"),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.decision is AdjudicationDecision.CONTRADICTED
    assert not result.verified


def test_unverified_receipt_does_not_claim_semantic_identity():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(decision="unverified"),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.decision is AdjudicationDecision.UNVERIFIED
    assert not result.verified


def test_same_actor_cannot_supply_independent_adjudication():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(adjudicator_id="provider-bonsai"),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.independence is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert not result.verified


def test_untrusted_adjudicator_cannot_verify():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(adjudicator_id="unregistered-panel"),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.origin is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert not result.verified


def test_untrusted_adjudicator_version_cannot_verify():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(adjudicator_version="rubric-v2"),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.origin is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert not result.verified


def test_binding_from_another_transition_cannot_be_reused():
    transition_a, binding_a = _binding()
    transition_b = BindingTransition(
        replace(transition_a.previous, id="snapshot-2"),
        replace(transition_a.current, id="snapshot-3"),
        replace(transition_a.question, id="question-1"),
    )
    result = evaluate_semantic_adjudication(
        _receipt(previous_snapshot_id="snapshot-2", current_snapshot_id="snapshot-3"),
        binding=binding_a,
        transition=transition_b,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.provenance is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert not result.verified


def test_binding_question_identity_is_part_of_adjudication_provenance():
    transition_a, binding_a = _binding()
    transition_b = BindingTransition(
        transition_a.previous,
        transition_a.current,
        replace(transition_a.question, id="question-1"),
    )
    result = evaluate_semantic_adjudication(
        _receipt(),
        binding=binding_a,
        transition=transition_b,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.provenance is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert not result.verified


def test_receipt_must_match_snapshot_lineage():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(previous_snapshot_id="stale"),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.provenance is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_receipt_must_match_claim_target_and_relation():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(target_id="other-target", relation="preserve"),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.provenance is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_receipt_must_use_the_expected_host_owned_basis():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        _receipt(basis_digest="b" * 64),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.provenance is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_structural_failure_cannot_be_upgraded_by_adjudication():
    transition = _transition()
    binding = evaluate_binding_claim(
        {
            "relation": "anchored_update",
            "target_id": "target-a",
            "target_kind": "Meaning",
            "source_target_id": "target-a",
            "previous_snapshot_id": "stale",
            "current_snapshot_id": "snapshot-1",
        },
        transition=transition,
        catalog=_catalog(),
    )
    assert not binding.structurally_admissible
    result = evaluate_semantic_adjudication(
        _receipt(),
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert not result.verified


def test_missing_receipt_is_not_comparable():
    transition, binding = _binding()
    result = evaluate_semantic_adjudication(
        None,
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        expected_basis_digest=BASIS_DIGEST,
        trusted_adjudicator_registry=TRUSTED_REGISTRY,
    )
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert result.schema is CheckStatus.NOT_APPLICABLE


def test_private_fields_are_rejected_from_adjudication_receipt():
    with pytest.raises(AdjudicationSchemaError, match="Unknown adjudication receipt fields"):
        parse_adjudication_receipt({**_receipt(), "provider_prompt": "private"})


def test_invalid_basis_digest_is_rejected_at_schema_boundary():
    with pytest.raises(AdjudicationSchemaError, match="lowercase SHA-256"):
        parse_adjudication_receipt(_receipt(basis_digest="not-a-digest"))
