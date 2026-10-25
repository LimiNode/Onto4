import importlib.util
import json
from pathlib import Path
import sys

import pytest


_PATH = Path(__file__).parents[1] / "research" / "pr56_target_binding_protocol.py"
_SPEC = importlib.util.spec_from_file_location("pr56_target_binding_protocol", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_protocol_freezes_three_conditions_and_two_scenarios():
    conditions, scenarios = _MODULE.default_protocol()
    manifest = _MODULE.public_manifest(conditions, scenarios)
    assert [condition["name"] for condition in manifest["conditions"]] == ["A", "B", "C"]
    assert len(manifest["scenarios"]) == 2
    assert manifest["live_run_performed"] is False
    assert manifest["semantic_oracle"] == "none"


def test_protocol_rejects_condition_reordering_and_duplicate_scenarios():
    conditions, scenarios = _MODULE.default_protocol()
    with pytest.raises(_MODULE.ProtocolError):
        _MODULE.validate_protocol((conditions[1], conditions[0], conditions[2]), scenarios)
    duplicate = (scenarios[0], _MODULE.Scenario(**{**scenarios[1].__dict__, "case_id": scenarios[0].case_id}))
    with pytest.raises(_MODULE.ProtocolError, match="case ids"):
        _MODULE.validate_protocol(conditions, duplicate)


def test_manifest_redacts_source_context_target_and_answer():
    conditions, scenarios = _MODULE.default_protocol()
    serialized = json.dumps(_MODULE.public_manifest(conditions, scenarios), ensure_ascii=False)
    assert "genome-identity-bounded" not in serialized
    assert "identity_and_genome" not in serialized
    assert "ambiguity-genome" not in serialized
    assert "numerical identity" not in serialized
    assert all(len(item["scenario_digest"]) == 64 for item in _MODULE.public_manifest(conditions, scenarios)["scenarios"])


def test_committed_protocol_manifest_matches_runner():
    artifact = Path(__file__).parents[3] / "docs" / "reports" / "pr56-target-binding-protocol.json"
    expected = _MODULE.public_manifest(*_MODULE.default_protocol())
    assert json.loads(artifact.read_text(encoding="utf-8")) == expected


def test_protocol_rejects_contradictory_condition_contracts():
    conditions, scenarios = _MODULE.default_protocol()
    contradictory = list(conditions)
    contradictory[0] = _MODULE.Condition("A", "full_snapshot", True, False, "successor_interpretation")
    with pytest.raises(_MODULE.ProtocolError):
        _MODULE.validate_protocol(tuple(contradictory), scenarios)


def test_protocol_manifest_preserves_historical_v1_digests():
    manifest = _MODULE.public_manifest(*_MODULE.default_protocol())
    assert manifest["protocol_version"] == "pr56-target-binding-v2"
    assert manifest["historical_protocol"]["version"] == "pr56-target-binding-v1"
    assert len(manifest["historical_protocol"]["scenario_digests"]) == 2
