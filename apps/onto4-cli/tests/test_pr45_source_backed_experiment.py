import importlib.util
from pathlib import Path
import sys


_SCRIPT_PATH = Path(__file__).parents[1] / "research" / "pr45_source_backed_experiment.py"
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
