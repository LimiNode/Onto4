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
    assert len(artifact["rows"]) == 8
    assert artifact["comparable_pair_count"] == 1
    assert artifact["non_comparable_pair_count"] == 7
    assert artifact["fail_closed_pair_count"] == 1
    assert all(
        row["A"]["question_intent_mismatch"]
        for row in artifact["rows"]
        if row["case_alias"] != "case-7"
    )

    comparable = next(
        item for item in artifact["rows"] if item["case_alias"] == "case-7"
    )
    assert comparable["comparison_class"] == "comparable"
    assert comparable["comparison_verdict"] == "no_observed_difference"
    assert comparable["A"]["question_intent_mismatch"] is False
    assert comparable["B"]["question_intent_mismatch"] is False


def test_host_binding_preserves_target_across_reindex_and_detects_churn():
    artifact = _SCRIPT.run_offline_experiment()
    row = next(item for item in artifact["rows"] if item["case_alias"] == "case-0")
    condition = row["B"]

    assert condition["stop_reason"] == "no_new_admissible_target"
    assert condition["target_preservation_count"] == 1
    assert condition["repeated_target_count"] == 0
    assert condition["structural_reduction_observed"] is False
    assert condition["structural_churn_observed"] is True


def test_host_binding_distinguishes_reduction_and_new_target_selection():
    artifact = _SCRIPT.run_offline_experiment()
    reduced = next(item for item in artifact["rows"] if item["case_alias"] == "case-1")
    new_target = next(item for item in artifact["rows"] if item["case_alias"] == "case-3")

    assert reduced["B"]["structural_reduction_observed"] is False
    assert reduced["B"]["stop_reason"] == "no_new_admissible_target"
    assert new_target["B"]["turns"] == 2
    assert new_target["B"]["repeated_target_count"] == 0
    assert new_target["B"]["stop_reason"] == "no_new_admissible_target"


def test_target_ledger_skips_unbound_first_ambiguity_and_uses_bound_target():
    artifact = _SCRIPT.run_offline_experiment()
    row = next(item for item in artifact["rows"] if item["case_alias"] == "case-6")

    assert row["B"]["turns"] == 1
    assert row["B"]["stop_reason"] == "no_admissible_question"
    assert row["B"]["unsupported_or_unbound"] is False
    assert row["B"]["structural_reduction_observed"] is True
    assert row["B"]["events"][0]["target_status"] == "preserve"


def test_unbound_target_stays_fail_closed_and_is_not_comparable():
    artifact = _SCRIPT.run_offline_experiment()
    row = next(item for item in artifact["rows"] if item["case_alias"] == "case-4")

    assert row["B"]["stop_reason"] == "unbound_target"
    assert row["B"]["unsupported_or_unbound"] is True
    assert row["comparison_class"] == "non_comparable"


def test_same_structural_reduction_with_different_lifecycle_is_not_no_difference():
    base = {
        "question_intent_mismatch": False,
        "unsupported_or_unbound": False,
        "question_count": 1,
        "structural_reduction_observed": True,
        "turns": 1,
        "stop_reason": "no_admissible_question",
        "target_preservation_count": 0,
        "retarget_count": 0,
        "repeated_target_count": 0,
        "structural_churn_observed": False,
    }
    changed = {**base, "stop_reason": "complete"}

    assert _SCRIPT._comparison_verdict(base, changed) == "not_comparable"


def test_no_progress_is_not_counted_as_reduction():
    artifact = _SCRIPT.run_offline_experiment()
    row = next(item for item in artifact["rows"] if item["case_alias"] == "case-5")

    assert row["B"]["stop_reason"] == "no_progress"
    assert row["B"]["structural_reduction_observed"] is False
    assert row["B"]["structural_churn_observed"] is False


def test_selected_target_is_preserved_when_bound_targets_are_reordered():
    fixture = _SCRIPT.FixtureCase(
        "comparable_control",
        snapshots=(
            _SCRIPT._space(
                "reordered-0",
                (
                    _SCRIPT.Ambiguity("amb-a", "identity", "A"),
                    _SCRIPT.Ambiguity("amb-b", "identity", "B"),
                ),
            ),
            _SCRIPT._space(
                "reordered-1",
                (
                    _SCRIPT.Ambiguity("amb-b", "identity", "B"),
                    _SCRIPT.Ambiguity("amb-a", "identity", "A"),
                ),
            ),
        ),
        answer_target_ids=("target-a", "target-b"),
        target_family=_SCRIPT.TARGET_FAMILY,
        host_bindings={
            "amb-a": ("target-a", _SCRIPT.TARGET_FAMILY),
            "amb-b": ("target-b", _SCRIPT.TARGET_FAMILY),
        },
    )

    result = _SCRIPT._run_condition(fixture, "B")

    assert result["events"][0]["transition_relation"] == "preserve"
    assert result["target_preservation_count"] == 1
    assert result["retarget_count"] == 0


def test_disappearing_selected_target_is_not_proven_retarget():
    fixture = _SCRIPT.FixtureCase(
        "comparable_control",
        snapshots=(
            _SCRIPT._space(
                "unverified-0",
                (_SCRIPT.Ambiguity("amb-a", "identity", "A"),),
            ),
            _SCRIPT._space(
                "unverified-1",
                (_SCRIPT.Ambiguity("amb-b", "identity", "B"),),
            ),
        ),
        answer_target_ids=("target-a", "target-b"),
        target_family=_SCRIPT.TARGET_FAMILY,
        host_bindings={
            "amb-a": ("target-a", _SCRIPT.TARGET_FAMILY),
            "amb-b": ("target-b", _SCRIPT.TARGET_FAMILY),
        },
    )

    result = _SCRIPT._run_condition(fixture, "B")

    assert result["events"][0]["transition_relation"] == "unverified_retarget"
    assert result["retarget_count"] == 0


def test_public_offline_artifact_contains_no_fixture_answers_or_target_ids():
    serialized = json.dumps(_SCRIPT.run_offline_experiment(), ensure_ascii=False)

    for private_value in (
        "target-identity",
        "target-new",
        "target-bound",
        "amb-0",
        "amb-new",
        "amb-bound",
        "amb-comparable",
        "identity-criterion",
        "fixture-answer",
    ):
        assert private_value not in serialized


def test_committed_offline_evidence_matches_current_runner_exactly():
    evidence_path = (
        Path(__file__).parents[3]
        / "docs"
        / "reports"
        / "pr49-offline-ab-20261024.json"
    )
    expected = _SCRIPT.run_offline_experiment()
    committed_text = evidence_path.read_text(encoding="utf-8")

    assert json.loads(committed_text) == expected
    assert committed_text == json.dumps(expected, ensure_ascii=False, indent=2) + "\n"
