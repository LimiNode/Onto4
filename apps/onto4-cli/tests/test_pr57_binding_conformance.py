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
