from dataclasses import replace

import pytest

from onto4.pipeline import (
    AdjudicationDecision,
    BindingTransition,
    CheckStatus,
    EvidenceNormalizationSchemaError,
    GENOME_IDENTITY_FIRST_TURN_BASIS,
    PublicSemanticTarget,
    SemanticTargetCatalog,
    evaluate_binding_claim,
    evaluate_independent_evidence_normalization,
    parse_independent_evidence_normalization,
)
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    InterpretationSpace,
)


SOURCE_DIGEST = "b" * 64
TRUSTED_NORMALIZERS = {"review-panel-1": "normalizer-v1"}


def _transition() -> BindingTransition:
    previous = InterpretationSpace(
        "snapshot-0",
        "Does sharing a genome make two people one person?",
        ConceptualDepth.Philosophical,
        ambiguities=(Ambiguity("a0", "genome", "old", target_id="ambiguity-genome"),),
    )
    current = replace(
        previous,
        id="snapshot-1",
        ambiguities=(Ambiguity("a1", "genome", "new", target_id="ambiguity-genome"),),
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-genome",
        kind=ClarificationKind.Meaning,
        text="What does sharing a genome mean here?",
        target_ids=("ambiguity-genome",),
    )
    return BindingTransition(previous, current, question)


def _binding():
    transition = _transition()
    binding = evaluate_binding_claim(
        {
            "relation": "anchored_update",
            "target_id": "ambiguity-genome",
            "target_kind": "Meaning",
            "source_target_id": "ambiguity-genome",
            "previous_snapshot_id": "snapshot-0",
            "current_snapshot_id": "snapshot-1",
        },
        transition=transition,
        catalog=SemanticTargetCatalog(
            1,
            {
                "ambiguity-genome": PublicSemanticTarget(
                    "ambiguity-genome", "Meaning", "genome sharing"
                )
            },
        ),
    )
    assert binding.structurally_admissible
    return transition, binding


def _normalization(**overrides):
    payload = {
        "case_id": "genome-identity-bounded",
        "previous_snapshot_id": "snapshot-0",
        "current_snapshot_id": "snapshot-1",
        "target_id": "ambiguity-genome",
        "question_id": "meaning:ambiguity-genome",
        "answer_ids": ["genome-2"],
        "relation": "anchored_update",
        "basis_digest": GENOME_IDENTITY_FIRST_TURN_BASIS.basis_digest,
        "normalizer_id": "review-panel-1",
        "normalizer_version": "normalizer-v1",
        "source_digest": SOURCE_DIGEST,
        "commitments": {"identity_criterion_is_numerical": "affirmed"},
    }
    payload.update(overrides)
    return payload


def _evaluate(payload, **overrides):
    transition, binding = _binding()
    overrides.setdefault("origin_attested", True)
    return evaluate_independent_evidence_normalization(
        payload,
        basis=GENOME_IDENTITY_FIRST_TURN_BASIS,
        binding=binding,
        transition=transition,
        provider_id="provider-bonsai",
        trusted_normalizer_registry=TRUSTED_NORMALIZERS,
        **overrides,
    )


def test_independent_normalization_can_verify_only_the_profile_commitment():
    result = _evaluate(_normalization())
    assert result.schema is CheckStatus.VALID
    assert result.provenance is CheckStatus.VALID
    assert result.origin is CheckStatus.VALID
    assert result.independence is CheckStatus.VALID
    assert result.decision is AdjudicationDecision.VERIFIED
    assert result.usable


def test_normalization_can_record_a_profile_contradiction():
    result = _evaluate(
        _normalization(commitments={"identity_criterion_is_numerical": "denied"})
    )
    assert result.decision is AdjudicationDecision.CONTRADICTED
    assert result.usable


def test_missing_normalization_is_not_comparable():
    result = _evaluate(None)
    assert result.schema is CheckStatus.NOT_APPLICABLE
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert not result.usable


@pytest.mark.parametrize(
    "overrides",
    [
        {"previous_snapshot_id": "stale"},
        {"question_id": "meaning:another-target"},
        {"target_id": "another-target"},
        {"relation": "preserve"},
        {"basis_digest": "a" * 64},
    ],
)
def test_normalization_must_match_exact_transition_claim_and_basis(overrides):
    result = _evaluate(_normalization(**overrides))
    assert result.provenance is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE
    assert not result.usable


def test_provider_cannot_normalize_its_own_output():
    result = _evaluate(_normalization(normalizer_id="provider-bonsai"))
    assert result.independence is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_untrusted_normalizer_or_version_is_rejected():
    result = _evaluate(_normalization(normalizer_version="normalizer-v2"))
    assert result.origin is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_host_origin_attestation_is_required():
    result = _evaluate(_normalization(), origin_attested=False)
    assert result.origin is CheckStatus.INVALID
    assert result.decision is AdjudicationDecision.NOT_COMPARABLE


def test_malformed_or_unknown_commitments_fail_closed():
    malformed = _evaluate(
        _normalization(commitments={"identity_criterion_is_numerical": "maybe"})
    )
    assert malformed.schema is CheckStatus.INVALID
    assert malformed.decision is AdjudicationDecision.NOT_COMPARABLE
    unknown = _evaluate(_normalization(commitments={"provider_confidence": "affirmed"}))
    assert unknown.schema is CheckStatus.INVALID
    assert unknown.decision is AdjudicationDecision.NOT_COMPARABLE


def test_public_envelope_rejects_private_source_text_and_invalid_digest():
    with pytest.raises(EvidenceNormalizationSchemaError, match="Unknown evidence normalization"):
        parse_independent_evidence_normalization(
            {**_normalization(), "source_text": "private model output"}
        )
    with pytest.raises(EvidenceNormalizationSchemaError, match="source_digest"):
        parse_independent_evidence_normalization(_normalization(source_digest="not-a-digest"))
