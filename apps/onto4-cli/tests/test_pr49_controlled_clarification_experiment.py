import importlib.util
import json
from pathlib import Path
import sys


_SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "research"
    / "pr49_controlled_clarification_experiment.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "pr49_controlled_clarification_experiment", _SCRIPT_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
_SCRIPT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCRIPT
_SPEC.loader.exec_module(_SCRIPT)


def test_offline_ab_fixture_gate_is_reproducible_and_bounded():
    artifact = _SCRIPT.run_offline_experiment()

    assert artifact["paired_initial_snapshot"] is True
    assert artifact["max_turns"] == 3
    assert artifact["live_run_performed"] is False
    assert artifact["semantic_identity"] == "not_evaluated"
    assert artifact["aggregate_verdict"] == "not_comparable"
    assert len(artifact["rows"]) == 6
    assert all(row["A"]["question_intent_mismatch"] for row in artifact["rows"])


def test_host_binding_preserves_target_across_reindex_and_detects_churn():
    artifact = _SCRIPT.run_offline_experiment()
    row = next(item for item in artifact["rows"] if item["case_alias"] == "case-0")
    condition = row["B"]

    assert condition["stop_reason"] == "max_turns_reached"
    assert condition["target_preservation_count"] == 3
    assert condition["repeated_target_count"] == 2
    assert condition["structural_reduction_observed"] is False
    assert condition["structural_churn_observed"] is True


def test_host_binding_distinguishes_reduction_and_fail_closed_new_target():
    artifact = _SCRIPT.run_offline_experiment()
    reduced = next(item for item in artifact["rows"] if item["case_alias"] == "case-1")
    new_target = next(item for item in artifact["rows"] if item["case_alias"] == "case-3")

    assert reduced["B"]["structural_reduction_observed"] is True
    assert reduced["B"]["stop_reason"] == "no_admissible_question"
    assert new_target["B"]["unsupported_or_unbound"] is True
    assert new_target["B"]["stop_reason"] == "unbound_target"


def test_no_progress_is_not_counted_as_reduction():
    artifact = _SCRIPT.run_offline_experiment()
    row = next(item for item in artifact["rows"] if item["case_alias"] == "case-5")

    assert row["B"]["stop_reason"] == "no_progress"
    assert row["B"]["structural_reduction_observed"] is False
    assert row["B"]["structural_churn_observed"] is False


def test_public_offline_artifact_contains_no_fixture_answers_or_target_ids():
    serialized = json.dumps(_SCRIPT.run_offline_experiment(), ensure_ascii=False)

    for private_value in (
        "target-identity",
        "amb-0",
        "amb-new",
        "identity-criterion",
        "fixture-answer",
    ):
        assert private_value not in serialized
