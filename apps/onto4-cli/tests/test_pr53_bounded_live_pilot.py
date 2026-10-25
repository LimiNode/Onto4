import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


_SCRIPT_PATH = Path(__file__).parents[1] / "research" / "pr53_bounded_live_pilot.py"
_SPEC = importlib.util.spec_from_file_location("pr53_bounded_live_pilot", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCRIPT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCRIPT
_SPEC.loader.exec_module(_SCRIPT)


def _evaluation():
    return SimpleNamespace(
        schema=SimpleNamespace(value="valid"),
        lineage=SimpleNamespace(value="valid"),
        transition=SimpleNamespace(value="valid"),
    )


def test_policy_arms_share_provider_protocol_but_have_different_ledger_behavior(monkeypatch):
    spec = _SCRIPT.base.CASES[0]

    def preserve(_client, _spec, current, _question, _catalog):
        return _SCRIPT.replace(_SCRIPT.base._initial(_spec), id=f"{current.id}-next"), _evaluation()

    monkeypatch.setattr(_SCRIPT.base, "_full_snapshot", preserve)
    a = _SCRIPT.run_condition(object(), spec, "A")
    b = _SCRIPT.run_condition(object(), spec, "B")

    assert a["provider_calls"] == 3
    assert a["stop_reason"] == "max_turns_reached"
    assert b["provider_calls"] == 1
    assert b["stop_reason"] == "no_new_admissible_target"
    assert a["semantic_identity"] == b["semantic_identity"] == "not_evaluated"


def test_target_loss_is_unverified_retarget_not_success(monkeypatch):
    spec = _SCRIPT.base.CASES[0]

    def lose_target(_client, _spec, current, _question, _catalog):
        successor = _SCRIPT.replace(_SCRIPT.base._initial(_spec), id=f"{current.id}-next", ambiguities=())
        return successor, _evaluation()

    monkeypatch.setattr(_SCRIPT.base, "_full_snapshot", lose_target)
    result = _SCRIPT.run_condition(object(), spec, "B")

    assert result["stop_reason"] == "unverified_retarget"
    assert result["unverified_retarget_count"] == 1
    assert result["target_preservation_count"] == 0


def test_pilot_uses_frozen_obligations_and_computes_pair_status(monkeypatch):
    def preserve(_client, _spec, current, _question, _catalog):
        return _SCRIPT.replace(current, id=f"{current.id}-next"), _evaluation()

    monkeypatch.setattr(_SCRIPT.base, "_full_snapshot", preserve)
    payload = _SCRIPT.run_pilot(object())
    assert payload["pilot_version"].endswith("v2")
    assert all(case["pair_comparability"] == "initial_matched_only" for case in payload["cases"])
    assert all(case["A"]["provider_calls"] == 3 for case in payload["cases"])
    assert all(case["B"]["provider_calls"] == 1 for case in payload["cases"])


def test_public_event_is_bounded():
    event = _SCRIPT._public_event(
        turn=0,
        question_issued=True,
        target_preserved=None,
        target_relation="PRIVATE_TARGET",
        provider_successor_valid=False,
        transition_provenance_valid=False,
        elapsed_seconds=1.25,
    )

    assert event["target_relation"] == "unknown"
    assert event["elapsed_seconds"] == 1.25


def test_committed_live_pilot_is_bounded_and_non_semantic():
    artifact_path = (
        Path(__file__).parents[3]
        / "docs"
        / "reports"
        / "pr53-live-pilot-20261025.json"
    )
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["max_cases"] == 2
    assert payload["max_turns"] == 3
    assert payload["aggregate_verdict"] == "not_comparable"
    assert payload["semantic_identity"] == "not_evaluated"
    assert payload["model_artifact_digest"] is None
    assert all(
        case[condition]["turns"] <= 3
        for case in payload["cases"]
        for condition in ("A", "B")
    )
    assert "ambiguity-genome" not in serialized
    assert "observer-independent" not in serialized
