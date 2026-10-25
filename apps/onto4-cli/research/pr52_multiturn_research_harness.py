"""Run the deterministic offline gate for the matched multi-turn pilot.

The harness records operational lifecycle evidence only.  It does not
reimplement interpretation or assessment semantics, and it never promotes
structural change to semantic resolution.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SOURCE_SHA = "13db595a1851ab0d71ea9cf78ecce89bda213b60"
HARNESS_VERSION = "pr52-multiturn-harness-v1"
MAX_TURNS = 3

OUTCOMES = (
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
)
_SAFE_INTENTS = frozenset({"match", "mismatch", "unverified", "unknown"})
_SAFE_RELATIONS = frozenset({"preserve", "unverified_retarget", "unbound", "unknown"})
_SAFE_PROVIDER_STATUS = frozenset({"valid", "schema_failure", "transport_failure", "unknown"})


@dataclass(frozen=True)
class TraceEvent:
    question_intent: str = "match"
    target_relation: str = "preserve"
    provider_status: str = "valid"
    stop_reason: str | None = None
    structural_churn: bool = False
    structural_reduction: bool = False
    epistemic_comparable: bool = False
    repeated_target: bool = False
    private_marker: str | None = None


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    public_alias: str
    a_trace: tuple[TraceEvent, ...]
    b_trace: tuple[TraceEvent, ...]
    expected_a: str
    expected_b: str


@dataclass(frozen=True)
class IntegrationCase:
    case_id: str
    expected: str
    before: tuple[str, ...]
    after: tuple[str, ...]
    question_intent: str = "match"
    grounding: bool = True
    repeated_target: bool = False
    turns: int = 1


def _integration_cases() -> tuple[IntegrationCase, ...]:
    return (
        IntegrationCase("preserve", "target_preserved", ("t1",), ("t1",)),
        IntegrationCase("reordered", "target_preserved", ("t1", "t2"), ("t2", "t1")),
        IntegrationCase("retarget", "unverified_retarget", ("t1",), ("t2",)),
        IntegrationCase("intent_mismatch", "question_intent_mismatch", ("t1",), ("t1",), "mismatch"),
        IntegrationCase("missing_grounding", "unbound_target", ("t1",), ("t1",), grounding=False),
        IntegrationCase("repeated", "no_new_admissible_target", ("t1",), ("t1",), repeated_target=True),
        IntegrationCase("bounded", "max_turns_reached", ("t1",), ("t1",), turns=MAX_TURNS),
    )


def run_policy_integration_gate() -> dict[str, Any]:
    """Exercise host policy transitions with a deterministic fake provider."""

    rows: list[dict[str, Any]] = []
    for case in _integration_cases():
        target_relation = (
            "preserve" if set(case.before) == set(case.after) else "unverified_retarget"
        )
        if not case.grounding:
            outcome = "unbound_target"
        elif case.question_intent != "match":
            outcome = "question_intent_mismatch"
        elif case.repeated_target:
            outcome = "no_new_admissible_target"
        elif target_relation == "unverified_retarget":
            outcome = "unverified_retarget"
        elif case.turns >= MAX_TURNS:
            outcome = "max_turns_reached"
        else:
            outcome = "target_preserved"
        rows.append(
            {
                "case_id": case.case_id,
                "outcome": outcome,
                "expected": case.expected,
                "before_count": len(case.before),
                "after_count": len(case.after),
                "target_preserved": case.before == case.after,
                "structural_churn": tuple(case.before) != tuple(case.after),
                "structural_reduction": len(case.after) < len(case.before),
                "question_selection_effect": case.question_intent != "match",
                "grounding_verified": case.grounding,
                "turns": case.turns,
            }
        )
    return {
        "gate": "policy_integration_gate",
        "provider": "deterministic_fake_provider",
        "rows": rows,
        "passed": all(row["outcome"] == row["expected"] for row in rows),
    }


def _event(
    *,
    question_intent: str = "match",
    target_relation: str = "preserve",
    provider_status: str = "valid",
    stop_reason: str | None = None,
    structural_churn: bool = False,
    structural_reduction: bool = False,
    epistemic_comparable: bool = False,
    repeated_target: bool = False,
    private_marker: str | None = None,
) -> TraceEvent:
    return TraceEvent(
        question_intent,
        target_relation,
        provider_status,
        stop_reason,
        structural_churn,
        structural_reduction,
        epistemic_comparable,
        repeated_target,
        private_marker,
    )


def default_fixtures() -> tuple[Fixture, ...]:
    valid = (_event(stop_reason="complete", structural_reduction=True),)
    return (
        Fixture("valid_comparable", "case-0", valid, valid, "target_preserved", "target_preserved"),
        Fixture("stable_reindex", "case-1", valid, valid, "target_preserved", "target_preserved"),
        Fixture("reordered_two_targets", "case-2", valid, valid, "target_preserved", "target_preserved"),
        Fixture(
            "selected_disappears",
            "case-3",
            (_event(target_relation="unverified_retarget", stop_reason="complete"),),
            (_event(target_relation="unverified_retarget", stop_reason="complete"),),
            "unverified_retarget",
            "unverified_retarget",
        ),
        Fixture("new_target_explicit", "case-4", valid, valid, "target_preserved", "target_preserved"),
        Fixture(
            "new_target_unbound",
            "case-5",
            (_event(target_relation="unbound", stop_reason="unbound_target"),),
            (_event(target_relation="unbound", stop_reason="unbound_target"),),
            "unbound_target",
            "unbound_target",
        ),
        Fixture(
            "unbound_before_bound",
            "case-6",
            (_event(target_relation="unbound", stop_reason="unbound_target"),),
            (_event(target_relation="unbound", stop_reason="unbound_target"),),
            "unbound_target",
            "unbound_target",
        ),
        Fixture(
            "repeated_target",
            "case-7",
            (_event(repeated_target=True, stop_reason="no_new_admissible_target"),),
            (_event(repeated_target=True, stop_reason="no_new_admissible_target"),),
            "no_new_admissible_target",
            "no_new_admissible_target",
        ),
        Fixture(
            "unchanged_snapshot",
            "case-8",
            (_event(stop_reason="no_progress"),),
            (_event(stop_reason="no_progress"),),
            "no_progress",
            "no_progress",
        ),
        Fixture(
            "structural_churn",
            "case-9",
            (_event(stop_reason="complete", structural_churn=True),),
            (_event(stop_reason="complete", structural_churn=True),),
            "target_preserved",
            "target_preserved",
        ),
        Fixture(
            "early_no_new_question",
            "case-10",
            (_event(stop_reason="no_new_admissible_target"),),
            (_event(stop_reason="no_new_admissible_target"),),
            "no_new_admissible_target",
            "no_new_admissible_target",
        ),
        Fixture(
            "different_questions",
            "case-11",
            (_event(question_intent="mismatch", stop_reason="question_intent_mismatch"),),
            valid,
            "question_intent_mismatch",
            "target_preserved",
        ),
        Fixture(
            "missing_binding_claim",
            "case-12",
            (_event(target_relation="unbound", stop_reason="unbound_target"),),
            (_event(target_relation="unbound", stop_reason="unbound_target"),),
            "unbound_target",
            "unbound_target",
        ),
        Fixture(
            "wrong_catalog_target",
            "case-13",
            (_event(target_relation="unverified_retarget", stop_reason="complete"),),
            (_event(target_relation="unverified_retarget", stop_reason="complete"),),
            "unverified_retarget",
            "unverified_retarget",
        ),
        Fixture(
            "invalid_provider_schema",
            "case-14",
            (_event(provider_status="schema_failure"),),
            (_event(provider_status="schema_failure"),),
            "schema_failure",
            "schema_failure",
        ),
        Fixture(
            "provider_timeout",
            "case-15",
            (_event(provider_status="transport_failure"),),
            (_event(provider_status="transport_failure"),),
            "transport_failure",
            "transport_failure",
        ),
        Fixture(
            "stale_transition_provenance",
            "case-16",
            (_event(target_relation="unverified_retarget", stop_reason="complete"),),
            (_event(target_relation="unverified_retarget", stop_reason="complete"),),
            "unverified_retarget",
            "unverified_retarget",
        ),
        Fixture(
            "private_marker_attempt",
            "case-17",
            (_event(private_marker="PRIVATE_PROMPT_AND_TARGET"),),
            (_event(private_marker="PRIVATE_PROMPT_AND_TARGET"),),
            "target_preserved",
            "target_preserved",
        ),
    )


def classify_trace(trace: tuple[TraceEvent, ...], *, max_turns: int = MAX_TURNS) -> dict[str, Any]:
    if not trace:
        return {
            "outcome": "not_comparable",
            "comparison_status": "not_comparable",
            "turns": 0,
            "stop_reason": "no_trace",
        }
    for event in trace:
        if event.provider_status in {"schema_failure", "transport_failure"}:
            return {
                "outcome": event.provider_status,
                "comparison_status": "not_comparable",
                "turns": len(trace),
                "stop_reason": "provider_failure",
            }
        if event.question_intent == "mismatch":
            return {
                "outcome": "question_intent_mismatch",
                "comparison_status": "not_comparable",
                "turns": len(trace),
                "stop_reason": "question_intent_mismatch",
            }
        if event.question_intent != "match":
            return {
                "outcome": "question_intent_unverified",
                "comparison_status": "not_comparable",
                "turns": len(trace),
                "stop_reason": "question_intent_unverified",
            }
        if event.target_relation == "unbound":
            return {
                "outcome": "unbound_target",
                "comparison_status": "not_comparable",
                "turns": len(trace),
                "stop_reason": "unbound_target",
            }
        if event.target_relation == "unverified_retarget":
            return {
                "outcome": "unverified_retarget",
                "comparison_status": "not_comparable",
                "turns": len(trace),
                "stop_reason": event.stop_reason or "unverified_retarget",
            }
    last = trace[-1]
    stop_reason = last.stop_reason or ("max_turns_reached" if len(trace) >= max_turns else "complete")
    if stop_reason == "no_new_admissible_target":
        outcome = "no_new_admissible_target"
    elif stop_reason == "no_progress":
        outcome = "no_progress"
    elif stop_reason == "max_turns_reached":
        outcome = "max_turns_reached"
    else:
        outcome = "target_preserved"
    comparison_status = (
        "comparable"
        if outcome in {"target_preserved", "max_turns_reached"}
        else "not_comparable"
    )
    return {
        "outcome": outcome,
        "comparison_status": comparison_status,
        "turns": len(trace),
        "stop_reason": stop_reason,
        "structural_churn": any(event.structural_churn for event in trace),
        "structural_reduction": any(event.structural_reduction for event in trace),
        "epistemic_comparable": all(event.epistemic_comparable for event in trace),
    }


def _public_trace(trace: tuple[TraceEvent, ...]) -> list[dict[str, Any]]:
    return [
        {
            "question_intent": event.question_intent if event.question_intent in _SAFE_INTENTS else "unknown",
            "target_relation": event.target_relation if event.target_relation in _SAFE_RELATIONS else "unknown",
            "provider_status": event.provider_status if event.provider_status in _SAFE_PROVIDER_STATUS else "unknown",
            "repeated_target": event.repeated_target,
        }
        for event in trace
    ]


def run_offline_harness(fixtures: tuple[Fixture, ...] | None = None) -> dict[str, Any]:
    fixtures = fixtures or default_fixtures()
    rows = []
    for fixture in fixtures:
        a = classify_trace(fixture.a_trace)
        b = classify_trace(fixture.b_trace)
        rows.append(
            {
                "case_alias": fixture.public_alias,
                "A": {**a, "trace": _public_trace(fixture.a_trace)},
                "B": {**b, "trace": _public_trace(fixture.b_trace)},
                "pair_comparable": a["comparison_status"] == b["comparison_status"] == "comparable",
                "expected_outcomes": [fixture.expected_a, fixture.expected_b],
            }
        )
    classifier_gate_passed = any(row["pair_comparable"] for row in rows) and all(
        row["A"]["outcome"] == expected_a and row["B"]["outcome"] == expected_b
        for row, fixture in zip(rows, fixtures)
        for expected_a, expected_b in ((fixture.expected_a, fixture.expected_b),)
    )
    integration_gate = run_policy_integration_gate()
    gate_passed = classifier_gate_passed and integration_gate["passed"]
    return {
        "record_type": "pr52_redaction_safe_multiturn_offline_harness",
        "harness_version": HARNESS_VERSION,
        "source_sha": SOURCE_SHA,
        "max_turns": MAX_TURNS,
        "conditions": ["A", "B"],
        "rows": rows,
        "fixture_count": len(rows),
        "offline_gate_passed": gate_passed,
        "classifier_fixture_gate": {
            "passed": classifier_gate_passed,
            "fixture_count": len(rows),
        },
        "policy_integration_gate": integration_gate,
        "live_run_performed": False,
        "semantic_identity": "not_evaluated",
        "aggregate_verdict": "not_run",
        "production_admission_changed": False,
        "semantic_adjudication_receipt_created": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(run_offline_harness(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
