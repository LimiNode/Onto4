import importlib.util
import json
from pathlib import Path
import sys

import pytest


_SCRIPT_PATH = Path(__file__).parents[1] / "research" / "pr52_multiturn_research_harness.py"
_SPEC = importlib.util.spec_from_file_location("pr52_multiturn_research_harness", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCRIPT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCRIPT
_SPEC.loader.exec_module(_SCRIPT)


def test_offline_harness_covers_all_required_fixture_classes_and_passes_gate():
    artifact = _SCRIPT.run_offline_harness()

    assert artifact["offline_gate_passed"] is True
    assert artifact["live_run_performed"] is False
    assert artifact["fixture_count"] == 18
    assert artifact["aggregate_verdict"] == "not_run"
    assert artifact["classifier_fixture_gate"]["passed"] is True
    assert artifact["policy_integration_gate"]["passed"] is True
    assert all(row["A"]["outcome"] in _SCRIPT.OUTCOMES for row in artifact["rows"])
    assert all(row["B"]["outcome"] in _SCRIPT.OUTCOMES for row in artifact["rows"])


@pytest.mark.parametrize(
    ("fixture_id", "expected"),
    (
        ("valid_comparable", "target_preserved"),
        ("selected_disappears", "unverified_retarget"),
        ("new_target_unbound", "unbound_target"),
        ("repeated_target", "no_new_admissible_target"),
        ("unchanged_snapshot", "no_progress"),
        ("different_questions", "question_intent_mismatch"),
        ("invalid_provider_schema", "schema_failure"),
        ("provider_timeout", "transport_failure"),
    ),
)
def test_required_fixture_classification_is_fail_closed(fixture_id, expected):
    fixture = next(item for item in _SCRIPT.default_fixtures() if item.fixture_id == fixture_id)
    result = _SCRIPT.classify_trace(fixture.a_trace)

    assert result["outcome"] == expected
    if expected != "target_preserved":
        assert result["comparison_status"] == "not_comparable"


def test_public_receipt_does_not_leak_private_marker_or_raw_trace_fields():
    serialized = json.dumps(_SCRIPT.run_offline_harness(), ensure_ascii=False)

    assert "PRIVATE_PROMPT_AND_TARGET" not in serialized
    assert "target-genome" not in serialized
    assert "numerical identity" not in serialized


def test_empty_trace_is_not_comparable():
    result = _SCRIPT.classify_trace(())

    assert result["outcome"] == "not_comparable"
    assert result["comparison_status"] == "not_comparable"


def test_policy_integration_gate_uses_snapshot_metrics_not_stop_reason():
    gate = _SCRIPT.run_policy_integration_gate()
    reordered = next(row for row in gate["rows"] if row["case_id"] == "reordered")
    assert reordered["outcome"] == "target_preserved"
    assert reordered["structural_churn"] is True
    assert reordered["structural_reduction"] is False


def test_public_trace_allowlist_replaces_unbounded_dynamic_strings():
    trace = (
        _SCRIPT.TraceEvent(
            question_intent="PRIVATE_PROMPT",
            target_relation="PRIVATE_TARGET",
            provider_status="PRIVATE_EXCEPTION",
            private_marker="PRIVATE_ANSWER",
        ),
    )

    serialized = json.dumps(_SCRIPT._public_trace(trace), ensure_ascii=False)

    assert "PRIVATE_" not in serialized
    assert "unknown" in serialized


def test_committed_harness_artifact_matches_runner_exactly():
    artifact_path = (
        Path(__file__).parents[3]
        / "docs"
        / "reports"
        / "pr52-multiturn-offline.json"
    )
    committed = artifact_path.read_text(encoding="utf-8")
    expected = _SCRIPT.run_offline_harness()

    assert json.loads(committed) == expected
    assert committed == json.dumps(expected, ensure_ascii=False, indent=2) + "\n"
