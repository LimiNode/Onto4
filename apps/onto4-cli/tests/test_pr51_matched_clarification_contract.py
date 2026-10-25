import importlib.util
import json
from pathlib import Path
import sys

import pytest


_SCRIPT_PATH = (
    Path(__file__).parents[1] / "research" / "pr51_matched_clarification_contract.py"
)
_SPEC = importlib.util.spec_from_file_location("pr51_matched_clarification_contract", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCRIPT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCRIPT
_SPEC.loader.exec_module(_SCRIPT)


def test_default_contract_freezes_two_matched_policy_conditions():
    conditions, scenarios = _SCRIPT.default_contract()
    _SCRIPT.validate_contract(conditions, scenarios)
    manifest = _SCRIPT.public_manifest(conditions, scenarios)

    assert [item["name"] for item in manifest["conditions"]] == ["A", "B"]
    assert manifest["conditions"][0]["provider_protocol_version"] == manifest["conditions"][1]["provider_protocol_version"]
    assert len(manifest["scenarios"]) == 2
    assert manifest["live_run_performed"] is False
    assert manifest["aggregate_verdict"] == "not_run"


def test_different_provider_protocol_is_rejected():
    conditions, scenarios = _SCRIPT.default_contract()
    altered = _SCRIPT.ProviderProtocol(
        version="different",
        model=conditions[1].provider_protocol.model,
        temperature=0.0,
        max_output_tokens=1024,
        thinking_enabled=False,
    )
    conditions = (conditions[0], _SCRIPT.ConditionSpec("B", "host_bound_target_policy", altered))

    with pytest.raises(_SCRIPT.ContractError, match="same provider protocol"):
        _SCRIPT.validate_contract(conditions, scenarios)


def test_changed_question_intent_is_not_comparable():
    scenario = _SCRIPT.default_contract()[1][0]

    assert (
        _SCRIPT.classify_question_intent(
            expected_target_family=scenario.target_family,
            actual_target_family="other-family",
            expected_target_id=scenario.target_id,
            actual_target_ids=(scenario.target_id,),
        )
        == "question_intent_mismatch"
    )
    assert (
        _SCRIPT.classify_question_intent(
            expected_target_family=scenario.target_family,
            actual_target_family=None,
            expected_target_id=scenario.target_id,
            actual_target_ids=None,
        )
        == "question_intent_unverified"
    )


def test_invalid_scenario_answer_obligations_fail_closed():
    conditions, scenarios = _SCRIPT.default_contract()
    invalid = _SCRIPT.ScenarioSpec(
        **{**scenarios[0].__dict__, "answer_obligations": ("one",)}
    )

    with pytest.raises(_SCRIPT.ContractError, match="three answer obligations"):
        _SCRIPT.validate_contract(conditions, (invalid, scenarios[1]))


def test_contract_manifest_serialization_is_deterministic_and_redacted():
    conditions, scenarios = _SCRIPT.default_contract()
    first = _SCRIPT.public_manifest(conditions, scenarios)
    second = _SCRIPT.public_manifest(conditions, scenarios)
    serialized = json.dumps(first, ensure_ascii=False, sort_keys=True)

    assert first == second
    assert "numerical identity" not in serialized
    assert "target-genome-identity" not in serialized
    assert all(len(item["host_input_digest"]) == 64 for item in first["scenarios"])


def test_executable_adapter_enforces_frozen_turn_and_question_contract():
    conditions, scenarios = _SCRIPT.default_contract()
    adapter = _SCRIPT.MatchedContractAdapter(conditions, scenarios)
    scenario = adapter.scenario("genome_identity")

    assert adapter.answer_obligation(scenario, 0).startswith("I mean numerical identity")
    assert adapter.validate_issued_question(
        scenario,
        question_kind=scenario.target_kind,
        target_family=scenario.target_family,
        target_ids=(scenario.target_id,),
    ) == "question_intent_match"
    assert adapter.validate_issued_question(
        scenario,
        question_kind=scenario.target_kind,
        target_family="wrong",
        target_ids=(scenario.target_id,),
    ) == "question_intent_mismatch"
    assert adapter.validate_issued_question(
        scenario,
        question_kind=scenario.target_kind,
        target_family=None,
        target_ids=(scenario.target_id,),
    ) == "question_intent_unverified"
    with pytest.raises(_SCRIPT.ContractError):
        adapter.answer_obligation(scenario, 3)


def test_executable_adapter_rejects_runner_identity_mismatch():
    conditions, scenarios = _SCRIPT.default_contract()
    adapter = _SCRIPT.MatchedContractAdapter(conditions, scenarios)
    scenario = scenarios[0]
    with pytest.raises(_SCRIPT.ContractError, match="source and context"):
        adapter.validate_runner_inputs(
            condition_names=("A", "B"),
            source_ids=("same", "different"),
            context_ids=("context", "context"),
            expected_source_id="same",
            expected_context_id="context",
            max_turns=3,
        )
    with pytest.raises(_SCRIPT.ContractError, match="actual frozen"):
        adapter.validate_runner_inputs(
            condition_names=("A", "B"),
            source_ids=(scenario.source_text, scenario.source_text),
            context_ids=("wrong", "wrong"),
            expected_source_id=scenario.source_text,
            expected_context_id=scenario.context_id,
            max_turns=3,
        )


def test_executable_adapter_rejects_wrong_kind_even_with_matching_family_and_id():
    conditions, scenarios = _SCRIPT.default_contract()
    adapter = _SCRIPT.MatchedContractAdapter(conditions, scenarios)
    scenario = scenarios[0]
    assert adapter.validate_issued_question(
        scenario,
        question_kind="Ontology",
        target_family=scenario.target_family,
        target_ids=(scenario.target_id,),
    ) == "question_intent_mismatch"


def test_adapter_metadata_is_safe_and_stable():
    conditions, scenarios = _SCRIPT.default_contract()
    adapter = _SCRIPT.MatchedContractAdapter(conditions, scenarios)
    metadata = adapter.safe_manifest_metadata()
    assert metadata["contract_version"] == _SCRIPT.PROTOCOL_VERSION
    assert len(metadata["scenario_digests"]) == 2
    assert "target-genome-identity" not in json.dumps(metadata)
