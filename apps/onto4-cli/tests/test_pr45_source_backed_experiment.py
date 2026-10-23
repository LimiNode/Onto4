import importlib.util
from pathlib import Path
import sys


_SCRIPT_PATH = Path(__file__).parents[1] / "research" / "pr45_source_backed_experiment.py"
sys.path.insert(0, str(_SCRIPT_PATH.parent))
from pr45_independent_corpus_normalizer import derive_identity_commitment


_SPEC = importlib.util.spec_from_file_location("pr45_source_backed_experiment", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCRIPT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCRIPT
_SPEC.loader.exec_module(_SCRIPT)


def test_source_backed_experiment_is_bounded_and_profile_relative():
    result = _SCRIPT.run_experiment()

    assert result["case_id"] == "genome-identity-bounded"
    assert result["scope"] == "public_host_dialogue_slice_first_turn"
    assert result["source"]["selected_turn_ids"] == ["genome-1", "genome-2"]
    assert result["source_manifest_evaluation"]["usable"] is True
    assert result["binding_structurally_admissible"] is True
    assert result["normalization_evaluation"]["decision"] == "verified"
    assert result["normalization_evaluation"]["usable"] is True
    assert result["profile_relative_result"] == "verified"
    assert result["historical_pr40_semantic_identity"] == "not_evaluated"


def test_source_digest_and_manifest_are_reproducible():
    first = _SCRIPT.run_experiment()
    second = _SCRIPT.run_experiment()

    assert first["source_manifest"]["source_digest"] == second["source_manifest"]["source_digest"]
    assert first["source_manifest"]["manifest_digest"] == second["source_manifest"]["manifest_digest"]
    assert first["normalization"]["basis_digest"] == second["normalization"]["basis_digest"]


def test_experiment_has_no_model_run_receipt_or_admission_side_effect():
    result = _SCRIPT.run_experiment()

    assert result["model_run_started"] is False
    assert result["historical_pr40_successor_used"] is False
    assert result["adjudication_receipt_created"] is False
    assert result["production_admission_changed"] is False


def test_content_changing_negative_control_is_not_verified():
    source = _SCRIPT._load_source_slice()
    source["answer"] = "I mean genetic similarity, not numerical identity."

    result = _SCRIPT.run_experiment(source)

    assert result["normalization"]["commitments"] == {
        "identity_criterion_is_numerical": "denied"
    }
    assert result["normalization_evaluation"]["decision"] == "contradicted"
    assert result["profile_relative_result"] == "contradicted"


def test_frozen_normalizer_handles_negation_without_keyword_guessing():
    assert derive_identity_commitment(
        "I mean numerical identity: they are one and the same individual."
    ) == "affirmed"
    assert derive_identity_commitment("I reject numerical identity.") == "denied"
    assert derive_identity_commitment(
        "I mean not genetic similarity, but numerical identity."
    ) == "affirmed"
    assert derive_identity_commitment(
        "I mean genetic similarity, not numerical identity."
    ) == "denied"
    assert derive_identity_commitment("Perhaps the relation needs clarification.") == "unspecified"


def test_rejection_of_numerical_identity_is_not_verified():
    source = _SCRIPT._load_source_slice()
    source["answer"] = "I reject numerical identity."

    result = _SCRIPT.run_experiment(source)

    assert result["normalization_evaluation"]["decision"] == "contradicted"
    assert result["profile_relative_result"] != "verified"


def test_negated_similarity_contrast_is_not_falsely_contradicted():
    source = _SCRIPT._load_source_slice()
    source["answer"] = "I mean not genetic similarity, but numerical identity."

    result = _SCRIPT.run_experiment(source)

    assert result["normalization_evaluation"]["decision"] == "verified"
    assert result["profile_relative_result"] == "verified"


def test_published_artifact_matches_reproduced_experiment():
    import json

    artifact_path = Path(__file__).parents[3] / "docs" / "reports" / "pr45-source-backed-experiment.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact == _SCRIPT.run_experiment()
