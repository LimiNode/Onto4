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


PROTOCOL_VERSION = "pr56-target-binding-v1"
SOURCE_SHA = "bf7d03ef6ababc9f7fedaea7b3e725071b4d0866"
MAX_SCENARIOS = 2


class ProtocolError(ValueError):
    """The frozen diagnostic protocol is invalid."""


@dataclass(frozen=True)
class Condition:
    name: str
    refinement_protocol: str
    binding_claim_required: bool
    target_focused_envelope: bool


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
        Condition("A", "full_snapshot", False, False),
        Condition("B", "explicit_binding", True, False),
        Condition("C", "minimal_target_focused", True, True),
    )
    scenarios = (
        Scenario(
            "genome-identity-bounded", "case-0",
            "Does sharing a genome make two people one person?",
            "identity_and_genome", "ambiguity-genome", "numerical_identity", "Meaning",
            "I mean numerical identity: they are one and the same individual.",
            "successor_plus_binding_claim",
            ("preserve", "anchored_update", "no_binding"),
        ),
        Scenario(
            "intrinsic-time-bounded", "case-1",
            "Does the sequence have an intrinsic present?",
            "intrinsic_time", "ambiguity-present", "observer_independent_present", "Meaning",
            "I mean an observer-independent present in the sequence itself.",
            "successor_plus_binding_claim",
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
        if not scenario.permitted_claims:
            raise ProtocolError("Scenario must freeze permitted binding claims.")


def public_manifest(
    conditions: tuple[Condition, ...], scenarios: tuple[Scenario, ...]
) -> dict[str, Any]:
    validate_protocol(conditions, scenarios)
    return {
        "record_type": "pr56_target_binding_diagnostic_protocol",
        "protocol_version": PROTOCOL_VERSION,
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
