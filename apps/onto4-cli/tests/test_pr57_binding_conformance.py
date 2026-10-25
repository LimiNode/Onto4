import importlib.util
import json
from pathlib import Path
import sys


_PATH = Path(__file__).parents[1] / "research" / "pr57_binding_conformance.py"
_SPEC = importlib.util.spec_from_file_location("pr57_binding_conformance", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_offline_gate_covers_binding_failure_classes_and_is_non_semantic():
    result = _MODULE.run_gate()
    assert result["offline_gate_passed"] is True
    assert result["semantic_correctness"] == "not_evaluated"
    assert result["live_run_performed"] is False
    assert len(result["rows"]) >= 10
    names = {row["fixture"] for row in result["rows"]}
    assert {"exact_target_preservation", "unknown_target_id", "duplicate_claims"} <= names


def test_committed_conformance_artifact_matches_runner():
    artifact = Path(__file__).parents[3] / "docs" / "reports" / "pr57-binding-conformance.json"
    assert json.loads(artifact.read_text(encoding="utf-8")) == _MODULE.run_gate()


def test_gate_rejects_unexpected_validator_outcome():
    rows = _MODULE.run_gate()["rows"]
    tampered = [dict(row) for row in rows]
    tampered[0]["transition"] = "invalid"
    assert _MODULE.validate_gate_rows(tampered) is False


def test_named_fixtures_construct_their_claimed_shapes():
    reordered, _ = _MODULE._transition(0, mode="reordered")
    assert len(reordered.previous.ambiguities) == 2
    assert tuple(item.target_id for item in reordered.previous.ambiguities) != tuple(
        item.target_id for item in reordered.current.ambiguities
    )
    wrong_object, target_id = _MODULE._transition(0, mode="wrong_object")
    assert not any(item.target_id == target_id for item in wrong_object.current.ambiguities)
    assert any(item.target_id == target_id for item in wrong_object.current.ontologies)
