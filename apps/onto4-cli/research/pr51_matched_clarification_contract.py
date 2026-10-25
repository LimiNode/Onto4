"""Freeze the matched clarification-selection A/B contract for PR #51.

This module defines an offline experiment contract only.  Both conditions use
the same provider/refinement protocol; the independent variable is the
clarification-selection policy.  It does not call a model and it does not
grant semantic authority to either policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


SOURCE_SHA = "a6ed465b25e3dd249d4cf259395fe9b1633f901c"
PROTOCOL_VERSION = "pr51-matched-clarification-v2"
PREVIOUS_PROTOCOL_VERSION = "pr51-matched-clarification-v1"
PROVIDER_PROTOCOL_VERSION = "shared-fixture-refinement-v1"
MAX_TURNS = 3
LEGACY_V1_SCENARIO_DIGESTS = {
    "case-0": "9eb676f8fb94871c0479730039db5ceddf2ff79d787550fe97f14b8572cd2e51",
    "case-1": "545fa39e634f4e003cfc504dc936470e7af3ca198020e6cb95cae312ac9ee207",
}


class ContractError(ValueError):
    """The frozen experiment contract is not safe to execute."""


@dataclass(frozen=True)
class ProviderProtocol:
    version: str
    model: str
    temperature: float
    max_output_tokens: int
    thinking_enabled: bool


@dataclass(frozen=True)
class ConditionSpec:
    name: str
    selection_policy: str
    provider_protocol: ProviderProtocol


@dataclass(frozen=True)
class ScenarioSpec:
    case_id: str
    public_alias: str
    source_text: str
    context_id: str
    target_family: str
    target_id: str
    question_kind: str
    answer_obligations: tuple[str, ...]
    max_turns: int = MAX_TURNS

    @property
    def target_kind(self) -> str:
        """Compatibility alias for pre-v2 callers; not a second field."""

        return self.question_kind


class MatchedContractAdapter:
    """Executable, research-only view of the frozen contract.

    The adapter is deliberately the only interface a runner needs.  It keeps
    source/context and target provenance host-owned and fails closed whenever a
    model-issued question cannot be matched to the frozen scenario.
    """

    def __init__(
        self,
        conditions: tuple[ConditionSpec, ...],
        scenarios: tuple[ScenarioSpec, ...],
    ) -> None:
        validate_contract(conditions, scenarios)
        self.conditions = conditions
        self.scenarios = scenarios
        self._by_case = {scenario.case_id: scenario for scenario in scenarios}
        if len(self._by_case) != len(scenarios):
            raise ContractError("Scenario case ids must be unique.")

    @property
    def protocol_version(self) -> str:
        return PROTOCOL_VERSION

    @property
    def provider_protocol(self) -> ProviderProtocol:
        return self.conditions[0].provider_protocol

    def scenario(self, case_id: str) -> ScenarioSpec:
        try:
            return self._by_case[case_id]
        except KeyError as exc:
            raise ContractError("Unknown frozen scenario.") from exc

    def answer_obligation(self, scenario: ScenarioSpec, turn: int) -> str:
        if not 0 <= turn < scenario.max_turns:
            raise ContractError("Turn is outside the frozen scenario bound.")
        return scenario.answer_obligations[turn]

    def validate_issued_question(
        self,
        scenario: ScenarioSpec,
        *,
        question_kind: str | None,
        target_family: str | None,
        target_ids: tuple[str, ...] | None,
    ) -> str:
        if question_kind is None or target_family is None or target_ids is None:
            return "question_intent_unverified"
        if (
            question_kind != scenario.question_kind
            or target_family != scenario.target_family
            or target_ids != (scenario.target_id,)
        ):
            return "question_intent_mismatch"
        return "question_intent_match"

    def validate_runner_inputs(
        self,
        *,
        condition_names: tuple[str, ...],
        source_ids: tuple[str, ...],
        context_ids: tuple[str, ...],
        expected_source_id: str,
        expected_context_id: str,
        max_turns: int,
        invocation_inputs: tuple[Mapping[str, Any], ...] = (),
    ) -> dict[str, Any]:
        if condition_names != ("A", "B"):
            raise ContractError("Runner must execute conditions A then B exactly once.")
        if (
            not expected_source_id
            or not expected_context_id
            or len(source_ids) != 2
            or len(context_ids) != 2
            or any(value != expected_source_id for value in source_ids)
            or any(value != expected_context_id for value in context_ids)
        ):
            raise ContractError("Conditions must use the actual frozen source and context identity.")
        if max_turns != MAX_TURNS:
            raise ContractError("Runner max_turns must match the frozen contract.")
        if invocation_inputs and len(invocation_inputs) != 2:
            raise ContractError("Runner must provide two invocation input snapshots.")
        host_consistent = all(
            snapshot.get("source_text") == expected_source_id
            and snapshot.get("context_id") == expected_context_id
            for snapshot in invocation_inputs
        ) if invocation_inputs else True
        if not host_consistent:
            raise ContractError("Provider invocation inputs do not match frozen source/context.")
        provider_attested = bool(invocation_inputs) and all(
            snapshot.get("provider_input_attested") is True
            for snapshot in invocation_inputs
        )
        return {
            "host_scenario_consistent": True,
            "provider_invocation_inputs_verified": provider_attested,
            "provider_context_not_independently_verified": not provider_attested,
        }

    def safe_manifest_metadata(self) -> dict[str, Any]:
        return {
            "contract_version": PROTOCOL_VERSION,
            "previous_contract_version": PREVIOUS_PROTOCOL_VERSION,
            "provider_protocol_version": self.provider_protocol.version,
            "scenario_count": len(self.scenarios),
            "scenario_digests": [host_input_digest(scenario) for scenario in self.scenarios],
        }


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def default_contract() -> tuple[tuple[ConditionSpec, ...], tuple[ScenarioSpec, ...]]:
    protocol = ProviderProtocol(
        version=PROVIDER_PROTOCOL_VERSION,
        model="Ternary-Bonsai-2-27B-PQ2_0.gguf",
        temperature=0.0,
        max_output_tokens=1024,
        thinking_enabled=False,
    )
    conditions = (
        ConditionSpec("A", "fixture_policy", protocol),
        ConditionSpec("B", "host_bound_target_policy", protocol),
    )
    scenarios = (
        ScenarioSpec(
            "genome_identity",
            "case-0",
            "Does sharing a genome make two people one person?",
            "identity_and_genome",
            "numerical_identity",
            "ambiguity-genome",
            "Meaning",
            (
                "I mean numerical identity: they are one and the same individual.",
                "Keep the numerical identity criterion explicit.",
                "Do not replace numerical identity with genetic similarity.",
            ),
        ),
        ScenarioSpec(
            "intrinsic_present",
            "case-1",
            "Does the sequence have an intrinsic present?",
            "intrinsic_time",
            "observer_independent_present",
            "ambiguity-present",
            "Meaning",
            (
                "I mean an observer-independent present in the sequence itself.",
                "Keep intrinsic present distinct from observation order.",
                "Do not replace intrinsic time with a human timestamp.",
            ),
        ),
    )
    return conditions, scenarios


def validate_contract(
    conditions: tuple[ConditionSpec, ...],
    scenarios: tuple[ScenarioSpec, ...],
) -> None:
    if {condition.name for condition in conditions} != {"A", "B"}:
        raise ContractError("Contract must contain exactly conditions A and B.")
    if len(conditions) != 2:
        raise ContractError("Contract must not contain duplicate conditions.")
    protocols = {condition.provider_protocol for condition in conditions}
    if len(protocols) != 1:
        raise ContractError("Both conditions must use the same provider protocol.")
    if not 1 <= len(scenarios) <= 2:
        raise ContractError("The matched pilot permits at most two scenarios.")
    aliases = [scenario.public_alias for scenario in scenarios]
    if len(set(aliases)) != len(aliases):
        raise ContractError("Scenario aliases must be unique.")
    for scenario in scenarios:
        if scenario.max_turns != MAX_TURNS:
            raise ContractError("Every scenario must have max_turns=3.")
        if not scenario.source_text.strip() or not scenario.context_id.strip():
            raise ContractError("Scenario source and context must be non-empty.")
        if not scenario.target_family.strip() or not scenario.target_id.strip():
            raise ContractError("Scenario target provenance must be explicit.")
        if len(scenario.answer_obligations) != MAX_TURNS:
            raise ContractError("Every scenario must freeze three answer obligations.")
        if any(not answer.strip() for answer in scenario.answer_obligations):
            raise ContractError("Answer obligations must be non-empty.")


def host_input_digest(scenario: ScenarioSpec) -> str:
    """Return a host-owned digest without publishing private scenario text."""

    return _digest(
        {
            "case_id": scenario.case_id,
            "source_text": scenario.source_text,
            "context_id": scenario.context_id,
            "target_family": scenario.target_family,
            "target_id": scenario.target_id,
            "question_kind": scenario.question_kind,
            "answer_obligations": scenario.answer_obligations,
            "max_turns": scenario.max_turns,
        }
    )


def classify_question_intent(
    *,
    expected_target_family: str,
    actual_target_family: str | None,
    expected_target_id: str,
    actual_target_ids: tuple[str, ...] | None,
) -> str:
    """Classify only host/question compatibility, never semantic correctness."""

    if actual_target_family is None or actual_target_ids is None:
        return "question_intent_unverified"
    if (
        actual_target_family != expected_target_family
        or actual_target_ids != (expected_target_id,)
    ):
        return "question_intent_mismatch"
    return "question_intent_match"


def public_manifest(
    conditions: tuple[ConditionSpec, ...],
    scenarios: tuple[ScenarioSpec, ...],
) -> dict[str, Any]:
    validate_contract(conditions, scenarios)
    protocol = conditions[0].provider_protocol
    return {
        "record_type": "pr51_matched_clarification_contract",
        "experiment_version": 2,
        "protocol_version": PROTOCOL_VERSION,
        "previous_protocol_version": PREVIOUS_PROTOCOL_VERSION,
        "previous_contract_source_sha": SOURCE_SHA,
        "source_sha": SOURCE_SHA,
        "provider_protocol": asdict(protocol),
        "conditions": [
            {
                "name": condition.name,
                "selection_policy": condition.selection_policy,
                "provider_protocol_version": condition.provider_protocol.version,
            }
            for condition in conditions
        ],
        "scenarios": [
            {
                "case_alias": scenario.public_alias,
                "question_kind": scenario.question_kind,
                "max_turns": scenario.max_turns,
                "answer_obligation_count": len(scenario.answer_obligations),
                "host_input_digest": host_input_digest(scenario),
                "previous_v1_host_input_digest": LEGACY_V1_SCENARIO_DIGESTS.get(
                    scenario.public_alias
                ),
                "permitted_outcomes": [
                    "comparable",
                    "question_intent_mismatch",
                    "question_intent_unverified",
                    "unbound_target",
                    "unverified_retarget",
                    "target_preserved",
                    "no_new_admissible_target",
                    "no_progress",
                    "schema_failure",
                    "transport_failure",
                    "max_turns_reached",
                    "not_comparable",
                    "inconclusive",
                ],
            }
            for scenario in scenarios
        ],
        "live_run_performed": False,
        "aggregate_verdict": "not_run",
        "semantic_identity": "not_evaluated",
        "production_admission_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    conditions, scenarios = default_contract()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(public_manifest(conditions, scenarios), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
