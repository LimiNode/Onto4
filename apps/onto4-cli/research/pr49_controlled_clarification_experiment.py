"""Run a deterministic A/B clarification-strategy experiment.

Condition A uses the current ``FixtureClarificationPolicy``.  Condition B
uses an explicit host-owned binding from snapshot-local ambiguity ids to a
stable semantic target family.  The harness is deliberately offline and
research-only: it records target relations and structural metrics, but never
publishes target ids, prompts, answers or semantic adjudication receipts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from onto4.reasoning import (
    Ambiguity,
    ClarificationContext,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    FixtureClarificationPolicy,
    InterpretationSpace,
    SemanticReading,
)
from onto4.reasoning.cross_candidate import AssessmentLandscape, CrossCandidateStatus


MAX_TURNS = 3
TARGET_FAMILY = "identity-criterion"
PUBLIC_CASE_ALIASES = {
    "repeat_target": "case-0",
    "changed_signature": "case-1",
    "disappears": "case-2",
    "new_ambiguity": "case-3",
    "unbound": "case-4",
    "no_progress": "case-5",
}


@dataclass(frozen=True)
class FixtureCase:
    case_id: str
    snapshots: tuple[InterpretationSpace, ...]
    answer_target_ids: tuple[str, ...]
    target_family: str
    host_bindings: Mapping[str, tuple[str, str]]


def _space(identifier: str, ambiguities: tuple[Ambiguity, ...]) -> InterpretationSpace:
    return InterpretationSpace(
        id=identifier,
        source_text="Does sharing a genome make two people one person?",
        conceptual_depth=ConceptualDepth.Philosophical,
        ambiguities=ambiguities,
        readings=(SemanticReading("reading-0", "identity", "identity criterion"),),
    )


def default_cases() -> tuple[FixtureCase, ...]:
    """Return paired immutable fixtures with explicit B-only host bindings."""

    return (
        FixtureCase(
            "repeat_target",
            snapshots=(
                _space("repeat-0", (Ambiguity("amb-0", "identity", "first"),)),
                _space("repeat-1", (Ambiguity("amb-1", "identity", "reworded"),)),
                _space("repeat-2", (Ambiguity("amb-2", "identity", "reworded again"),)),
                _space("repeat-3", (Ambiguity("amb-3", "identity", "still open"),)),
            ),
            answer_target_ids=("target-identity",) * MAX_TURNS,
            target_family=TARGET_FAMILY,
            host_bindings={
                "amb-0": ("target-identity", TARGET_FAMILY),
                "amb-1": ("target-identity", TARGET_FAMILY),
                "amb-2": ("target-identity", TARGET_FAMILY),
                "amb-3": ("target-identity", TARGET_FAMILY),
            },
        ),
        FixtureCase(
            "changed_signature",
            snapshots=(
                _space("signature-0", (Ambiguity("amb-0", "identity", "before"),)),
                _space("signature-1", (Ambiguity("amb-0", "identity", "changed"),)),
                _space("signature-2", ()),
            ),
            answer_target_ids=("target-identity", "target-identity"),
            target_family=TARGET_FAMILY,
            host_bindings={"amb-0": ("target-identity", TARGET_FAMILY)},
        ),
        FixtureCase(
            "disappears",
            snapshots=(
                _space("disappear-0", (Ambiguity("amb-0", "identity", "open"),)),
                _space("disappear-1", ()),
            ),
            answer_target_ids=("target-identity",),
            target_family=TARGET_FAMILY,
            host_bindings={"amb-0": ("target-identity", TARGET_FAMILY)},
        ),
        FixtureCase(
            "new_ambiguity",
            snapshots=(
                _space("new-0", (Ambiguity("amb-0", "identity", "open"),)),
                _space("new-1", (Ambiguity("amb-new", "identity", "new"),)),
                _space("new-2", (Ambiguity("amb-new", "identity", "new"),)),
            ),
            answer_target_ids=("target-identity", "target-identity"),
            target_family=TARGET_FAMILY,
            host_bindings={"amb-0": ("target-identity", TARGET_FAMILY)},
        ),
        FixtureCase(
            "unbound",
            snapshots=(
                _space("unbound-0", (Ambiguity("amb-0", "identity", "open"),)),
            ),
            answer_target_ids=(),
            target_family=TARGET_FAMILY,
            host_bindings={},
        ),
        FixtureCase(
            "no_progress",
            snapshots=(
                _space("no-progress-0", (Ambiguity("amb-0", "identity", "open"),)),
                _space("no-progress-0", (Ambiguity("amb-0", "identity", "open"),)),
            ),
            answer_target_ids=("target-identity",),
            target_family=TARGET_FAMILY,
            host_bindings={"amb-0": ("target-identity", TARGET_FAMILY)},
        ),
    )


def _context(snapshot: InterpretationSpace) -> ClarificationContext:
    landscape = AssessmentLandscape(
        assessments=(),
        status=CrossCandidateStatus.StableAcrossCandidates,
    )
    return ClarificationContext(
        interpretation=snapshot,
        candidates=(),
        assessments=(),
        landscape=landscape,
    )


def _fixture_question(snapshot: InterpretationSpace) -> ClarificationQuestion | None:
    questions = FixtureClarificationPolicy().questions(_context(snapshot))
    return questions[0] if questions else None


def _bound_question(
    snapshot: InterpretationSpace,
    bindings: Mapping[str, tuple[str, str]],
) -> ClarificationQuestion | None:
    if not snapshot.ambiguities:
        return None
    ambiguity = snapshot.ambiguities[0]
    binding = bindings.get(ambiguity.id)
    if binding is None:
        return None
    target_id, target_family = binding
    return ClarificationQuestion(
        id=f"host:{target_family}",
        kind=ClarificationKind.Meaning,
        text="Host-bound identity clarification",
        target_ids=(target_id,),
        target_family=target_family,
        structural_target_ids=(ambiguity.id,),
    )


def _target(snapshot: InterpretationSpace, bindings: Mapping[str, tuple[str, str]]) -> str | None:
    if not snapshot.ambiguities:
        return None
    binding = bindings.get(snapshot.ambiguities[0].id)
    return binding[0] if binding is not None else None


def _run_condition(case: FixtureCase, condition: str) -> dict[str, Any]:
    bindings = {} if condition == "A" else case.host_bindings
    selector = _fixture_question if condition == "A" else lambda snapshot: _bound_question(snapshot, bindings)
    current_index = 0
    turns = 0
    selected_targets: list[str] = []
    events: list[dict[str, Any]] = []
    stop_reason = "max_turns_reached"
    mismatch = False
    unbound = False

    while turns < MAX_TURNS:
        snapshot = case.snapshots[current_index]
        question = selector(snapshot)
        if question is None:
            stop_reason = "unbound_target" if condition == "B" and snapshot.ambiguities else "no_admissible_question"
            unbound = stop_reason == "unbound_target"
            break
        expected_target = (
            case.answer_target_ids[turns]
            if turns < len(case.answer_target_ids)
            else None
        )
        intent_match = (
            expected_target is not None
            and question.target_family == case.target_family
            and question.target_ids == (expected_target,)
        )
        event: dict[str, Any] = {
            "turn_index": turns,
            "question_alias": f"question-{turns}",
            "snapshot_alias": f"snapshot-{current_index}",
            "question_intent_match": intent_match,
            "question_intent_mismatch": not intent_match,
            "target_status": "preserve" if _target(snapshot, bindings) else "unbound",
            "repeated_target": bool(_target(snapshot, bindings) in selected_targets),
        }
        events.append(event)
        if not intent_match:
            mismatch = True
            stop_reason = "question_intent_mismatch"
            break
        selected_target = _target(snapshot, bindings)
        if selected_target is not None:
            selected_targets.append(selected_target)
        turns += 1
        if current_index + 1 >= len(case.snapshots):
            stop_reason = "complete"
            break
        next_snapshot = case.snapshots[current_index + 1]
        current_target = _target(snapshot, bindings)
        next_target = _target(next_snapshot, bindings)
        relation = (
            "preserve"
            if current_target is not None and current_target == next_target
            else "retarget"
            if next_target is not None
            else "unbound"
        )
        event["transition_relation"] = relation
        event["structural_changed"] = snapshot != next_snapshot
        current_index += 1
        if not event["structural_changed"]:
            stop_reason = "no_progress"
            break

    initial_count = len(case.snapshots[0].ambiguities)
    final_count = len(case.snapshots[current_index].ambiguities)
    changed = any(item.get("structural_changed") for item in events)
    return {
        "condition": condition,
        "case_alias": PUBLIC_CASE_ALIASES[case.case_id],
        "turns": turns,
        "stop_reason": stop_reason,
        "question_count": len(events),
        "question_intent_mismatch": mismatch,
        "unsupported_or_unbound": unbound,
        "target_preservation_count": sum(
            item.get("transition_relation") == "preserve" for item in events
        ),
        "retarget_count": sum(
            item.get("transition_relation") == "retarget" for item in events
        ),
        "repeated_target_count": sum(item["repeated_target"] for item in events),
        "initial_ambiguity_count": initial_count,
        "final_ambiguity_count": final_count,
        "structural_reduction_observed": final_count < initial_count,
        "structural_churn_observed": changed and final_count >= initial_count,
        "events": events,
    }


def _comparison_verdict(a: Mapping[str, Any], b: Mapping[str, Any]) -> str:
    if a["question_intent_mismatch"] or b["question_intent_mismatch"]:
        return "not_comparable"
    a_reduction = a["structural_reduction_observed"]
    b_reduction = b["structural_reduction_observed"]
    if b_reduction and not a_reduction:
        return "B_better_observed"
    if a_reduction and not b_reduction:
        return "A_better_observed"
    if a_reduction == b_reduction:
        return "no_observed_difference"
    return "inconclusive"


def run_offline_experiment(cases: tuple[FixtureCase, ...] | None = None) -> dict[str, Any]:
    cases = cases or default_cases()
    rows: list[dict[str, Any]] = []
    for case in cases:
        a = _run_condition(case, "A")
        b = _run_condition(case, "B")
        rows.append(
            {
                "case_alias": PUBLIC_CASE_ALIASES[case.case_id],
                "A": a,
                "B": b,
                "comparison_verdict": _comparison_verdict(a, b),
            }
        )
    verdicts = [row["comparison_verdict"] for row in rows]
    aggregate = "inconclusive"
    if verdicts and all(item == "no_observed_difference" for item in verdicts):
        aggregate = "no_observed_difference"
    elif any(item == "not_comparable" for item in verdicts):
        aggregate = "not_comparable"
    return {
        "record_type": "pr49_redaction_safe_controlled_clarification_offline",
        "experiment_version": 1,
        "conditions": {"A": "fixture_policy", "B": "host_bound_target_policy"},
        "max_turns": MAX_TURNS,
        "paired_initial_snapshot": True,
        "rows": rows,
        "aggregate_verdict": aggregate,
        "live_run_performed": False,
        "production_admission_changed": False,
        "semantic_adjudication_receipt_created": False,
        "semantic_identity": "not_evaluated",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(run_offline_experiment(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
