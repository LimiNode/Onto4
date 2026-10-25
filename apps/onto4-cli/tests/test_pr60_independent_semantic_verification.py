import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import sys


_PATH = Path(__file__).parents[1] / "research" / "pr60_independent_semantic_verification.py"
_SPEC = importlib.util.spec_from_file_location("pr60_independent_semantic_verification", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_fixture_matrix_covers_independent_semantic_cases():
    result = _MODULE.run_offline_protocol()
    names = {row["fixture"] for row in result["rows"]}
    assert names == {
        "same_semantics_same_id",
        "same_semantics_different_id",
        "wrong_semantics_correct_id",
        "ambiguity_genuinely_resolved",
        "ambiguity_merely_omitted",
        "semantic_relationship_indeterminate",
        "untrusted_observation",
        "provider_self_report_without_evidence",
        "missing_normalizer_provenance",
        "duplicate_evidence_source",
        "contradictory_evidence",
        "apparent_resolution_without_evidence",
    }
    assert result["semantic_adjudication_receipt_created"] is False
    assert all(row["synthetic_oracle_fixture"] is True for row in result["rows"])


def test_same_semantics_different_id_is_semantically_correct_but_not_literal_retention():
    row = _MODULE.run_offline_protocol()["rows"][1]
    assert row["semantic_alignment"] == "correct"
    assert row["literal_id_retention"] is False


def test_wrong_semantics_with_correct_id_is_incorrect():
    row = _MODULE.run_offline_protocol()["rows"][2]
    assert row["semantic_alignment"] == "incorrect"
    assert row["literal_id_retention"] is True


def test_omission_and_indeterminate_resolution_are_not_passes():
    rows = _MODULE.run_offline_protocol()["rows"]
    assert rows[4]["ambiguity_resolution"] == "unverified"
    assert rows[5]["ambiguity_resolution"] == "unverified"


def test_provider_self_report_cannot_change_result():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    provenance = _MODULE.ObservationProvenance("obs", "normalizer", "v1", "source", _MODULE.EvidenceAuthority.HOST_INDEPENDENT)
    evidence = (_MODULE.EvidenceReference("source", _MODULE.EvidenceAuthority.HOST_INDEPENDENT, _MODULE.EvidenceStatus.VERIFIED, "evidence"),)
    observed = _MODULE.ObservedSemanticSnapshot("wrong", "id-x", _MODULE.ResolutionStatus.RESOLVED, evidence, provenance)
    trusted = _MODULE.verify_independent(expected, observed, provider_claim={"target": "x"})
    hostile = _MODULE.verify_independent(expected, observed, provider_claim={"target": "wrong"})
    assert trusted == hostile


def test_missing_provenance_is_unverified_even_when_labels_match():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    observed = _MODULE.ObservedSemanticSnapshot("x", "id-x", _MODULE.ResolutionStatus.RESOLVED)
    result = _MODULE.verify_independent(expected, observed)
    assert result.semantic_alignment == _MODULE.SemanticStatus.UNVERIFIED


def test_provider_authority_cannot_become_independent_evidence():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    provenance = _MODULE.ObservationProvenance("obs", "normalizer", "v1", "provider", _MODULE.EvidenceAuthority.PROVIDER)
    evidence = (_MODULE.EvidenceReference("provider", _MODULE.EvidenceAuthority.PROVIDER, _MODULE.EvidenceStatus.VERIFIED, "evidence"),)
    observed = _MODULE.ObservedSemanticSnapshot("x", "id-x", _MODULE.ResolutionStatus.RESOLVED, evidence, provenance)
    result = _MODULE.verify_independent(expected, observed)
    assert result.ambiguity_resolution == _MODULE.SemanticStatus.UNVERIFIED


def _apparently_verified_observation(*, source="source-a", normalizer="normalizer"):
    provenance = _MODULE.ObservationProvenance(
        "obs", normalizer, "v1", "source-a", _MODULE.EvidenceAuthority.HOST_INDEPENDENT
    )
    evidence = (
        _MODULE.EvidenceReference(
            source,
            _MODULE.EvidenceAuthority.HOST_INDEPENDENT,
            _MODULE.EvidenceStatus.VERIFIED,
            "evidence",
        ),
    )
    return _MODULE.ObservedSemanticSnapshot(
        "x", "id-x", _MODULE.ResolutionStatus.RESOLVED, evidence, provenance
    )


def _trusted_resolver(expected, observed):
    provenance = observed.provenance
    assert provenance is not None
    attestation = _MODULE.HostEvidenceAttestation(
        expected.target_key,
        provenance.observation_id,
        provenance.normalizer_id,
        provenance.normalizer_version,
        provenance.source_id,
        tuple(evidence.source_id for evidence in observed.evidence),
        tuple(evidence.statement_key for evidence in observed.evidence),
        _MODULE._observation_digest(expected, observed),
    )
    return _MODULE.TrustedHostEvidenceResolver(frozenset((attestation,)))


def test_forged_verified_fields_without_resolver_fail_closed():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    result = _MODULE.verify_independent(expected, _apparently_verified_observation())
    assert result.semantic_alignment == _MODULE.SemanticStatus.UNVERIFIED
    assert "resolver" in result.reason


def test_trusted_resolver_attests_exact_observation_evidence_relationship():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    observed = _apparently_verified_observation()
    resolver = _trusted_resolver(expected, observed)
    result = _MODULE.verify_independent(expected, observed, resolver=resolver)
    assert result.semantic_alignment == _MODULE.SemanticStatus.CORRECT
    assert result.result_scope == "trusted_host_evidence"


def test_unrelated_evidence_source_and_unverifiable_normalizer_fail_closed():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    resolver = _trusted_resolver(expected, _apparently_verified_observation())
    unrelated = _MODULE.verify_independent(
        expected, _apparently_verified_observation(source="source-b"), resolver=resolver
    )
    bad_normalizer = _MODULE.verify_independent(
        expected, _apparently_verified_observation(normalizer="unknown"), resolver=resolver
    )
    assert unrelated.semantic_alignment == _MODULE.SemanticStatus.UNVERIFIED
    assert bad_normalizer.semantic_alignment == _MODULE.SemanticStatus.UNVERIFIED


def test_invalid_mode_values_fail_closed_before_resolver_validation():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    observed = _apparently_verified_observation()
    resolver = _trusted_resolver(expected, observed)
    for invalid_mode in ("real_observation", "synthetic_fixture", "unknown", None, object()):
        result = _MODULE.verify_independent(
            expected, observed, mode=invalid_mode, resolver=resolver
        )
        assert result.semantic_alignment == _MODULE.SemanticStatus.UNVERIFIED
        assert result.result_scope == "unverified"
        assert result.reason == "verification mode is invalid"


def test_attestation_cannot_be_reused_for_changed_observation_content():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    original = _apparently_verified_observation()
    resolver = _trusted_resolver(expected, original)
    assert _MODULE.verify_independent(expected, original, resolver=resolver).semantic_alignment is _MODULE.SemanticStatus.CORRECT

    variants = (
        replace(original, target_key="other"),
        replace(original, resolution=_MODULE.ResolutionStatus.OMITTED),
        replace(original, target_id="other-id"),
        replace(original, evidence=(replace(original.evidence[0], statement_key="other"),)),
        replace(original, evidence=(replace(original.evidence[0], status=_MODULE.EvidenceStatus.UNVERIFIED),)),
    )
    for altered in variants:
        result = _MODULE.verify_independent(expected, altered, resolver=resolver)
        assert result.semantic_alignment == _MODULE.SemanticStatus.UNVERIFIED
        assert result.result_scope == "unverified"


def test_contradictory_evidence_has_specific_fail_closed_reason():
    expected = _MODULE.SemanticExpectation("x", "id-x", ("evidence",))
    observed = _apparently_verified_observation()
    contradictory = replace(
        observed,
        evidence=(
            replace(
                observed.evidence[0], status=_MODULE.EvidenceStatus.CONTRADICTORY
            ),
        ),
    )
    result = _MODULE.verify_independent(expected, contradictory)
    assert result.semantic_alignment == _MODULE.SemanticStatus.UNVERIFIED
    assert result.reason == "evidence is contradictory"


def test_committed_protocol_artifact_matches_deterministic_runner():
    artifact = Path(__file__).parents[3] / "docs" / "reports" / "pr60-independent-semantic-verification.json"
    assert json.loads(artifact.read_text(encoding="utf-8")) == _MODULE.run_offline_protocol()
