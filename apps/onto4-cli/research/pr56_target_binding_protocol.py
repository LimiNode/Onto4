"""Freeze the provider target-binding diagnostic protocol.

This is a research-only manifest.  It fixes the question, answer, target and
provider protocol before execution and does not treat any provider output as a
semantic oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "pr56-target-binding-v2"
HISTORICAL_PROTOCOL_VERSION = "pr56-target-binding-v1"
SOURCE_SHA = "bf7d03ef6ababc9f7fedaea7b3e725071b4d0866"
MAX_SCENARIOS = 2
HISTORICAL_V1_SCENARIO_DIGESTS = (
    "4e9fa3243362651cd352f1ee8d415ffffcf2a9c597a7a35ead90848f60423944",
    "0e7023016fe00fe91ae052ef14607a62d91399dcd9b1a58683af7a5db615d13c",
)


class ProtocolError(ValueError):
    """The frozen diagnostic protocol is invalid."""


@dataclass(frozen=True)
class Condition:
    name: str
    refinement_protocol: str
    binding_claim_required: bool
    target_focused_envelope: bool
    response_schema: str


@dataclass(frozen=True)
class Scenario:
    case_id: str
    public_alias: str
    source_text: str
    context_id: str
    target_id: str
    target_family: str
    question_kind: str
    answer: str
    response_schema: str
    permitted_claims: tuple[str, ...]


def default_protocol() -> tuple[tuple[Condition, ...], tuple[Scenario, ...]]:
    conditions = (
        Condition("A", "full_snapshot", False, False, "successor_interpretation"),
        Condition("B", "explicit_binding", True, False, "successor_plus_binding_claim"),
        Condition("C", "minimal_target_focused", True, True, "minimal_successor_plus_binding_claim"),
    )
    scenarios = (
        Scenario(
            "genome-identity-bounded", "case-0",
            "Does sharing a genome make two people one person?",
            "identity_and_genome", "ambiguity-genome", "numerical_identity", "Meaning",
            "I mean numerical identity: they are one and the same individual.",
            "condition_specific",
            ("preserve", "anchored_update", "no_binding"),
        ),
        Scenario(
            "intrinsic-time-bounded", "case-1",
            "Does the sequence have an intrinsic present?",
            "intrinsic_time", "ambiguity-present", "observer_independent_present", "Meaning",
            "I mean an observer-independent present in the sequence itself.",
            "condition_specific",
            ("preserve", "anchored_update", "no_binding"),
        ),
    )
    return conditions, scenarios


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def scenario_digest(scenario: Scenario) -> str:
    return _digest(asdict(scenario))


def validate_protocol(
    conditions: tuple[Condition, ...], scenarios: tuple[Scenario, ...]
) -> None:
    if tuple(condition.name for condition in conditions) != ("A", "B", "C"):
        raise ProtocolError("Conditions must be exactly A, B, C in that order.")
    expected_conditions = (
        Condition("A", "full_snapshot", False, False, "successor_interpretation"),
        Condition("B", "explicit_binding", True, False, "successor_plus_binding_claim"),
        Condition("C", "minimal_target_focused", True, True, "minimal_successor_plus_binding_claim"),
    )
    if conditions != expected_conditions:
        raise ProtocolError("Condition names, protocols and response obligations must agree.")
    if len(scenarios) != MAX_SCENARIOS:
        raise ProtocolError("Protocol must contain exactly two frozen scenarios.")
    if len({scenario.case_id for scenario in scenarios}) != len(scenarios):
        raise ProtocolError("Scenario case ids must be unique.")
    if len({scenario.public_alias for scenario in scenarios}) != len(scenarios):
        raise ProtocolError("Scenario aliases must be unique.")
    for scenario in scenarios:
        if not all(
            value.strip()
            for value in (
                scenario.source_text,
                scenario.context_id,
                scenario.target_id,
                scenario.target_family,
                scenario.question_kind,
                scenario.answer,
                    scenario.response_schema,
            )
        ):
                raise ProtocolError("Scenario identity and answer fields must be non-empty.")
        if scenario.response_schema != "condition_specific":
            raise ProtocolError("Scenario response schema must defer to condition-specific contracts.")
        if not scenario.permitted_claims:
            raise ProtocolError("Scenario must freeze permitted binding claims.")
        if len(set(scenario.permitted_claims)) != len(scenario.permitted_claims):
            raise ProtocolError("Scenario permitted claims must be unique.")
    expected_schemas = {
        "A": "successor_interpretation",
        "B": "successor_plus_binding_claim",
        "C": "minimal_successor_plus_binding_claim",
    }
    for condition in conditions:
        if condition.refinement_protocol not in {"full_snapshot", "explicit_binding", "minimal_target_focused"}:
            raise ProtocolError("Unsupported refinement protocol.")
        if condition.name not in expected_schemas:
            raise ProtocolError("Unknown condition name.")
        if condition.response_schema != expected_schemas[condition.name]:
            raise ProtocolError("Condition response schema does not match its obligations.")
        if condition.name == "A" and condition.binding_claim_required:
            raise ProtocolError("Full Snapshot must not require a binding claim.")
        if condition.name != "A" and not condition.binding_claim_required:
            raise ProtocolError("Binding conditions must require a binding claim.")
        if condition.name == "C" and not condition.target_focused_envelope:
            raise ProtocolError("Minimal target-focused condition must mark its envelope.")
        if condition.name != "C" and condition.target_focused_envelope:
            raise ProtocolError("Only condition C may use the target-focused envelope.")


def public_manifest(
    conditions: tuple[Condition, ...], scenarios: tuple[Scenario, ...]
) -> dict[str, Any]:
    validate_protocol(conditions, scenarios)
    return {
        "record_type": "pr56_target_binding_diagnostic_protocol",
        "protocol_version": PROTOCOL_VERSION,
        "historical_protocol": {
            "version": HISTORICAL_PROTOCOL_VERSION,
            "scenario_digests": list(HISTORICAL_V1_SCENARIO_DIGESTS),
        },
        "source_sha": SOURCE_SHA,
        "conditions": [asdict(condition) for condition in conditions],
        "scenarios": [
            {
                "case_alias": scenario.public_alias,
                "question_kind": scenario.question_kind,
                "response_schema": scenario.response_schema,
                "permitted_claims": list(scenario.permitted_claims),
                "scenario_digest": scenario_digest(scenario),
            }
            for scenario in scenarios
        ],
        "measured_outcomes": [
            "schema_validity", "binding_claim_validity", "literal_target_preservation",
            "catalog_validity", "lineage_validity", "structural_ambiguity_counts",
            "independent_semantic_evidence", "semantic_correctness_not_evaluated",
        ],
        "semantic_oracle": "none",
        "live_run_performed": False,
        "production_admission_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    conditions, scenarios = default_protocol()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(public_manifest(conditions, scenarios), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
