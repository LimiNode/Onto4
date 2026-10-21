from dataclasses import replace

import pytest

from onto4.pipeline import (
    BindingTransition,
    CheckStatus,
    GENOME_IDENTITY_FIRST_TURN_BASIS,
    IndependentEvidenceNormalization,
    SourceManifest,
    SourceManifestSchemaError,
    canonical_source_digest,
    evaluate_source_manifest,
    parse_source_manifest,
)
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    InterpretationSpace,
)


SOURCE_DIGEST = "b" * 64


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


def _normalization() -> IndependentEvidenceNormalization:
    return IndependentEvidenceNormalization(
        case_id="genome-identity-bounded",
        previous_snapshot_id="snapshot-0",
        current_snapshot_id="snapshot-1",
        target_id="ambiguity-genome",
        question_id="meaning:ambiguity-genome",
        answer_ids=("genome-2",),
        relation=GENOME_IDENTITY_FIRST_TURN_BASIS.relation,
        basis_digest=GENOME_IDENTITY_FIRST_TURN_BASIS.basis_digest,
        normalizer_id="review-panel-1",
        normalizer_version="normalizer-v1",
        source_digest=SOURCE_DIGEST,
        commitments={"identity_criterion_is_numerical": "affirmed"},
    )

def _manifest(**overrides):
    payload = {
        "manifest_id": "source-manifest-1",
        "version": "v1",
        "source_id": "pr40-private-successor-pair",
        "source_kind": "provider_snapshot_pair",
        "source_digest": SOURCE_DIGEST,
        "canonicalization": "utf8-lf-sha256-v1",
        "previous_snapshot_id": "snapshot-0",
        "current_snapshot_id": "snapshot-1",
        "question_id": "meaning:ambiguity-genome",
        "access_attested": True,
    }
    payload.update(overrides)
    return payload


def _trusted_registry(payload=None):
    return {
        "source-manifest-1": parse_source_manifest(payload or _manifest()).manifest_digest
    }


def test_host_manifest_binds_normalization_to_selected_source_and_transition():
    result = evaluate_source_manifest(
        _manifest(),
        normalization=_normalization(),
        transition=_transition(),
        trusted_manifest_registry=_trusted_registry(),
    )
    assert result.schema is CheckStatus.VALID
    assert result.provenance is CheckStatus.VALID
    assert result.custody is CheckStatus.VALID
    assert result.transition is CheckStatus.VALID
    assert result.usable


@pytest.mark.parametrize(
    "overrides, status",
    [
        ({"source_digest": "c" * 64}, "provenance"),
        ({"previous_snapshot_id": "stale"}, "transition"),
        ({"question_id": "meaning:other"}, "transition"),
        ({"access_attested": False}, "custody"),
    ],
)
def test_manifest_mismatch_fails_closed(overrides, status):
    result = evaluate_source_manifest(
        _manifest(**overrides),
        normalization=_normalization(),
        transition=_transition(),
        trusted_manifest_registry=_trusted_registry(_manifest(**overrides)),
    )
    assert getattr(result, status) is CheckStatus.INVALID
    assert not result.usable


def test_untrusted_manifest_content_fails_closed():
    result = evaluate_source_manifest(
        _manifest(source_id="different-source"),
        normalization=_normalization(),
        transition=_transition(),
        trusted_manifest_registry=_trusted_registry(),
    )
    assert result.provenance is CheckStatus.INVALID
    assert not result.usable


def test_parser_rejects_unknown_mixed_keys_and_unsupported_canonicalization():
    payload = _manifest()
    payload[1] = "unknown"
    with pytest.raises(SourceManifestSchemaError, match="Unknown source manifest fields"):
        parse_source_manifest(payload)
    with pytest.raises(SourceManifestSchemaError, match="Unsupported source manifest canonicalization"):
        parse_source_manifest(_manifest(canonicalization="raw-sha256"))


def test_normalization_from_another_transition_cannot_reuse_manifest_digest():
    foreign = replace(_normalization(), previous_snapshot_id="snapshot-2", current_snapshot_id="snapshot-3")
    result = evaluate_source_manifest(
        _manifest(),
        normalization=foreign,
        transition=_transition(),
        trusted_manifest_registry=_trusted_registry(),
    )
    assert result.transition is CheckStatus.INVALID
    assert not result.usable


def test_normalization_target_must_belong_to_host_question():
    foreign = replace(_normalization(), target_id="another-target")
    result = evaluate_source_manifest(
        _manifest(),
        normalization=foreign,
        transition=_transition(),
        trusted_manifest_registry=_trusted_registry(),
    )
    assert result.transition is CheckStatus.INVALID
    assert not result.usable


def test_typed_manifest_uses_the_same_schema_invariants_as_mapping():
    malformed = SourceManifest(
        manifest_id="source-manifest-1",
        version="v1",
        source_id="example",
        source_kind="provider_snapshot_pair",
        source_digest="not-a-digest",
        canonicalization="unsupported",
        previous_snapshot_id="snapshot-0",
        current_snapshot_id="snapshot-1",
        question_id="meaning:ambiguity-genome",
        access_attested="yes",
    )
    result = evaluate_source_manifest(
        malformed,
        normalization=_normalization(),
        transition=_transition(),
        trusted_manifest_registry=_trusted_registry(),
    )
    assert result.schema is CheckStatus.INVALID
    assert not result.usable


def test_canonical_source_digest_has_cross_platform_golden_vectors():
    assert canonical_source_digest("one\nline\n") == (
        "d37dffbad51bfd37985bda02caed144496ffa7ee406850575d3c2024675a2fc0"
    )
    assert canonical_source_digest("one\r\nline\r\n") == (
        "d37dffbad51bfd37985bda02caed144496ffa7ee406850575d3c2024675a2fc0"
    )
    assert canonical_source_digest("Привет, Onto4\n") == (
        "777d73ff4ede9117ddc7c52fabb6a211d1ba8110af863b149123e87dee6aef85"
    )


def test_canonical_source_digest_requires_text():
    with pytest.raises(TypeError, match="input must be text"):
        canonical_source_digest(b"bytes")
