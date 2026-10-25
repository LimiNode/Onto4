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
PROTOCOL_VERSION = "pr51-matched-clarification-v1"
PROVIDER_PROTOCOL_VERSION = "shared-fixture-refinement-v1"
MAX_TURNS = 3


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
    target_kind: str
    answer_obligations: tuple[str, ...]
    max_turns: int = MAX_TURNS


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
        target_family: str | None,
        target_ids: tuple[str, ...] | None,
    ) -> str:
        return classify_question_intent(
            expected_target_family=scenario.target_family,
            actual_target_family=target_family,
            expected_target_id=scenario.target_id,
            actual_target_ids=target_ids,
        )

    def validate_runner_inputs(
        self,
        *,
        condition_names: tuple[str, ...],
        source_ids: tuple[str, ...],
        context_ids: tuple[str, ...],
        max_turns: int,
    ) -> None:
        if condition_names != ("A", "B"):
            raise ContractError("Runner must execute conditions A then B exactly once.")
        if len(set(source_ids)) != 1 or len(set(context_ids)) != 1:
            raise ContractError("Conditions must share source and context identity.")
        if max_turns != MAX_TURNS:
            raise ContractError("Runner max_turns must match the frozen contract.")

    def safe_manifest_metadata(self) -> dict[str, Any]:
        return {
            "contract_version": PROTOCOL_VERSION,
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
            "target-genome-identity",
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
            "target-intrinsic-present",
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
            "target_kind": scenario.target_kind,
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
        "experiment_version": 1,
        "protocol_version": PROTOCOL_VERSION,
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
                "target_kind": scenario.target_kind,
                "max_turns": scenario.max_turns,
                "answer_obligation_count": len(scenario.answer_obligations),
                "host_input_digest": host_input_digest(scenario),
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
