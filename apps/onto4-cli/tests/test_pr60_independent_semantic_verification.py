import importlib.util
import json
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


def test_committed_protocol_artifact_matches_deterministic_runner():
    artifact = Path(__file__).parents[3] / "docs" / "reports" / "pr60-independent-semantic-verification.json"
    assert json.loads(artifact.read_text(encoding="utf-8")) == _MODULE.run_offline_protocol()
