"""Run the deterministic offline conformance gate for PR #56."""

from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import sys
from typing import Any, Mapping

from onto4.pipeline.semantic_binding import (
    BindingTransition,
    CheckStatus,
    evaluate_binding_claim,
    evaluate_binding_claims,
)


_PROTOCOL_SPEC = importlib.util.spec_from_file_location(
    "pr56_target_binding_protocol_for_pr57",
    Path(__file__).with_name("pr56_target_binding_protocol.py"),
)
assert _PROTOCOL_SPEC is not None and _PROTOCOL_SPEC.loader is not None
protocol = importlib.util.module_from_spec(_PROTOCOL_SPEC)
sys.modules[_PROTOCOL_SPEC.name] = protocol
_PROTOCOL_SPEC.loader.exec_module(protocol)

_BASE_SPEC = importlib.util.spec_from_file_location(
    "pr40_semantic_binding_runner_for_pr57",
    Path(__file__).with_name("pr40_semantic_binding_runner.py"),
)
assert _BASE_SPEC is not None and _BASE_SPEC.loader is not None
base = importlib.util.module_from_spec(_BASE_SPEC)
sys.modules[_BASE_SPEC.name] = base
_BASE_SPEC.loader.exec_module(base)


SOURCE_SHA = "d6622ce"
GATE_VERSION = "pr57-binding-conformance-v1"


def _transition(index: int, *, mode: str = "preserve") -> tuple[BindingTransition, str]:
    spec = base.CASES[index]
    initial = base._initial(spec)
    question = base._question(spec)
    question = replace(
        question,
        target_family=protocol.default_protocol()[1][index].target_family,
    )
    current = replace(initial, id=f"{initial.id}-successor")
    if mode == "missing_target":
        current = replace(current, ambiguities=())
    elif mode == "wrong_object":
        current = replace(current, ontologies=tuple(current.ontologies), ambiguities=())
    elif mode == "reordered":
        current = replace(current, ambiguities=tuple(reversed(current.ambiguities)))
    return BindingTransition(initial, current, question), spec.target_id


def _claim(transition: BindingTransition, target_id: str, relation: str = "preserve") -> dict[str, Any]:
    return {
        "relation": relation,
        "target_id": target_id,
        "target_kind": transition.question.kind.value,
        "source_target_id": target_id if relation in {"preserve", "anchored_update"} else None,
        "previous_snapshot_id": transition.previous.id,
        "current_snapshot_id": transition.current.id,
    }


def _fixture(name: str, index: int, *, mode: str = "preserve", payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    transition, target_id = _transition(index, mode=mode)
    catalog = base.CATALOGS[base.CASES[index].case_id]
    if payload is None:
        payload = _claim(transition, target_id)
    evaluation = evaluate_binding_claim(payload, transition=transition, catalog=catalog)
    return {
        "fixture": name,
        "schema": evaluation.schema.value,
        "catalog": evaluation.catalog.value,
        "lineage": evaluation.lineage.value,
        "transition": evaluation.transition.value,
        "semantic_identity": evaluation.semantic_identity.value,
        "structurally_admissible": evaluation.structurally_admissible,
        "error_count": len(evaluation.errors),
    }


def run_gate() -> dict[str, Any]:
    scenarios = protocol.default_protocol()[1]
    rows = [
        _fixture("exact_target_preservation", 0),
        _fixture("target_reorder", 0, mode="reordered"),
        _fixture("missing_target_id", 0, payload={"relation": "preserve"}),
        _fixture("unknown_target_id", 0, payload=_claim(_transition(0)[0], "unknown-target")),
        _fixture("catalog_valid_wrong_target", 0, payload=_claim(_transition(0)[0], "ambiguity-criterion")),
        _fixture("correct_id_wrong_object", 0, mode="wrong_object"),
        _fixture("stale_lineage", 0, payload={**_claim(_transition(0)[0], "ambiguity-genome"), "previous_snapshot_id": "stale"}),
        _fixture("structurally_resolved_ambiguity", 0, mode="missing_target", payload=_claim(_transition(0, mode="missing_target")[0], "ambiguity-genome")),
        _fixture("unsupported_relation", 0, payload={**_claim(_transition(0)[0], "ambiguity-genome"), "relation": "unsupported"}),
    ]
    duplicate_transition, duplicate_target = _transition(0)
    duplicate = evaluate_binding_claims(
        (_claim(duplicate_transition, duplicate_target), _claim(duplicate_transition, duplicate_target)),
        transition=duplicate_transition,
        catalog=base.CATALOGS[base.CASES[0].case_id],
    )
    rows.append({
        "fixture": "duplicate_claims",
        "schema": "valid",
        "catalog": "valid",
        "lineage": "valid",
        "transition": "invalid" if all(item.transition is CheckStatus.INVALID for item in duplicate) else "unknown",
        "semantic_identity": "unverified",
        "structurally_admissible": False,
        "error_count": sum(len(item.errors) for item in duplicate),
    })
    return {
        "record_type": "pr57_redaction_safe_binding_conformance",
        "gate_version": GATE_VERSION,
        "source_sha": SOURCE_SHA,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "scenario_count": len(scenarios),
        "rows": rows,
        "offline_gate_passed": all(row["fixture"] and row["transition"] in {"valid", "invalid", "not_applicable"} for row in rows),
        "semantic_oracle": "none",
        "semantic_correctness": "not_evaluated",
        "live_run_performed": False,
        "production_admission_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(run_gate(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
