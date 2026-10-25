"""Run the bounded matched live Bonsai pilot for PR #53.

Both arms use the same Full Snapshot refinement protocol.  The only research
variable is host-side question selection: A may repeat a target, while B keeps
a host-owned ledger and will not issue that target again without new evidence.
The public receipt is operational and redaction-safe; it makes no semantic
claim.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import sys
import time
from typing import Any

from onto4.reasoning import ClarificationContext, FixtureClarificationPolicy
from onto4.reasoning.cross_candidate import AssessmentLandscape, CrossCandidateStatus
from onto4.providers import OpenAICompatibleClient, ProviderProfile

_CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "pr51_matched_contract_for_pr53",
    Path(__file__).with_name("pr51_matched_clarification_contract.py"),
)
assert _CONTRACT_SPEC is not None and _CONTRACT_SPEC.loader is not None
contract_module = importlib.util.module_from_spec(_CONTRACT_SPEC)
sys.modules[_CONTRACT_SPEC.name] = contract_module
_CONTRACT_SPEC.loader.exec_module(contract_module)


_BASE_SPEC = importlib.util.spec_from_file_location(
    "pr40_semantic_binding_runner_for_pr53",
    Path(__file__).with_name("pr40_semantic_binding_runner.py"),
)
assert _BASE_SPEC is not None and _BASE_SPEC.loader is not None
base = importlib.util.module_from_spec(_BASE_SPEC)
sys.modules[_BASE_SPEC.name] = base
_BASE_SPEC.loader.exec_module(base)


SOURCE_SHA = "495ea38"
PILOT_VERSION = "pr53-bounded-live-pilot-v2"
PROVIDER_PROTOCOL_VERSION = "pr40-full-snapshot-v1"
MAX_TURNS = 3
CONDITION_ORDER = ("A", "B")


def _context(snapshot):
    return ClarificationContext(
        interpretation=snapshot,
        candidates=(),
        assessments=(),
        landscape=AssessmentLandscape(
            assessments=(), status=CrossCandidateStatus.StableAcrossCandidates
        ),
    )


def _policy(spec, condition: str):
    family = f"host:{spec.case_id}"
    base_policy = FixtureClarificationPolicy(
        semantic_target_families={spec.target_id: family},
        require_semantic_target_families=True,
    )
    selected: set[str] = set()

    def choose(snapshot):
        questions = base_policy.questions(_context(snapshot))
        if condition == "B":
            questions = tuple(
                question
                for question in questions
                if not set(question.target_ids) & selected
            )
        return questions[0] if questions else None

    return choose, selected


def _safe_failure(exc: Exception) -> str:
    code = getattr(exc, "code", type(exc).__name__)
    if not isinstance(code, str):
        return "provider_failure"
    lowered = code.lower()
    if "schema" in lowered:
        return "schema_failure"
    if "transport" in lowered or "timeout" in lowered or "connection" in lowered:
        return "transport_failure"
    return "provider_failure"


def _public_event(
    *,
    turn: int,
    question_issued: bool,
    target_preserved: bool | None,
    target_relation: str,
    provider_successor_valid: bool,
    transition_provenance_valid: bool,
    elapsed_seconds: float | None,
) -> dict[str, Any]:
    return {
        "turn": turn,
        "question_issued": question_issued,
        "target_preserved": target_preserved,
        "target_relation": target_relation
        if target_relation in {"preserve", "lost", "unverified_retarget", "unbound"}
        else "unknown",
        "provider_successor_valid": provider_successor_valid,
        "transition_provenance_valid": transition_provenance_valid,
        "elapsed_seconds": (
            round(max(0.0, min(float(elapsed_seconds), 86_400.0)), 3)
            if elapsed_seconds is not None
            else None
        ),
    }


def run_condition(
    client: OpenAICompatibleClient,
    spec: base.CaseSpec,
    condition: str,
    *,
    max_turns: int = MAX_TURNS,
    scenario: Any | None = None,
    adapter: Any | None = None,
) -> dict[str, Any]:
    initial = base._initial(spec)
    catalog = base.CATALOGS[spec.case_id]
    choose, selected = _policy(spec, condition)
    current = initial
    events: list[dict[str, Any]] = []
    stop_reason = "max_turns_reached"
    provider_calls = 0
    question_intent_status = "host_verified"
    before_signatures: list[tuple[Any, ...]] = []
    after_signatures: list[tuple[Any, ...]] = []

    for turn in range(max_turns):
        question = choose(current)
        if question is None:
            stop_reason = "no_new_admissible_target" if condition == "B" else "unbound_target"
            events.append(
                _public_event(
                    turn=turn,
                    question_issued=False,
                    target_preserved=None,
                    target_relation="unbound",
                    provider_successor_valid=True,
                    transition_provenance_valid=True,
                    elapsed_seconds=None,
                )
            )
            break
        if scenario is not None and adapter is not None:
            question_intent_status = adapter.validate_issued_question(
                scenario,
                target_family=question.kind.value,
                target_ids=tuple(question.target_ids),
            )
            if question_intent_status != "question_intent_match":
                stop_reason = "question_intent_mismatch" if question_intent_status == "question_intent_mismatch" else "question_intent_unverified"
                events.append(
                    _public_event(
                        turn=turn,
                        question_issued=True,
                        target_preserved=None,
                        target_relation="unknown",
                        provider_successor_valid=False,
                        transition_provenance_valid=False,
                        elapsed_seconds=None,
                    )
                )
                break
        selected.update(question.target_ids)
        started = time.perf_counter()
        provider_calls += 1
        try:
            invocation_spec = (
                replace(spec, answer=adapter.answer_obligation(scenario, turn))
                if scenario is not None and adapter is not None
                else spec
            )
            before_signatures.append(_structure_signature(current))
            successor, evaluation = base._full_snapshot(
                client, invocation_spec, current, question, catalog
            )
            elapsed = time.perf_counter() - started
            successor = replace(successor, id=f"{spec.case_id}-{condition}-snapshot-{turn + 1}")
            target_preserved = base._target_present(successor, spec.target_id)
            after_signatures.append(_structure_signature(successor))
            relation = "preserve" if target_preserved else "lost"
            events.append(
                _public_event(
                    turn=turn,
                    question_issued=True,
                    target_preserved=target_preserved,
                    target_relation=relation,
                    provider_successor_valid=evaluation.schema.value == "valid",
                    transition_provenance_valid=evaluation.lineage.value == "valid"
                    and evaluation.transition.value == "valid",
                    elapsed_seconds=elapsed,
                )
            )
            if not target_preserved:
                stop_reason = "unverified_retarget"
                break
            current = successor
        except Exception as exc:
            elapsed = time.perf_counter() - started
            code = _safe_failure(exc)
            events.append(
                _public_event(
                    turn=turn,
                    question_issued=True,
                    target_preserved=None,
                    target_relation="unknown",
                    provider_successor_valid=False,
                    transition_provenance_valid=False,
                    elapsed_seconds=elapsed,
                )
            )
            stop_reason = code
            break
    else:
        stop_reason = "max_turns_reached"

    structural_reduction = any(
        sum(after) < sum(before)
        for before, after in zip(before_signatures, after_signatures)
    )
    structural_churn = any(before != after for before, after in zip(before_signatures, after_signatures))
    return {
        "condition": condition,
        "turns": sum(event["question_issued"] for event in events),
        "provider_calls": provider_calls,
        "stop_reason": stop_reason,
        "question_intent_status": question_intent_status,
        "target_preservation_count": sum(
            event["target_relation"] == "preserve" for event in events
        ),
        "unverified_retarget_count": sum(
            event["target_relation"] in {"unverified_retarget", "lost"}
            for event in events
        ),
        "structural_reduction_observed": structural_reduction,
        "structural_churn_observed": structural_churn,
        "semantic_identity": "not_evaluated",
        "events": events,
    }


def _structure_signature(snapshot: Any) -> tuple[Any, ...]:
    """Compare host snapshots without publishing their content or IDs."""

    return (
        len(getattr(snapshot, "ambiguities", ())),
        len(getattr(snapshot, "presuppositions", ())),
        len(getattr(snapshot, "ontologies", ())),
        len(getattr(snapshot, "readings", ())),
    )


def _pair_comparability(a: dict[str, Any], b: dict[str, Any]) -> str:
    if a.get("question_intent_status") != "question_intent_match" or b.get("question_intent_status") != "question_intent_match":
        return "not_comparable"
    if a.get("stop_reason") == b.get("stop_reason") == "unverified_retarget":
        return "initial_matched_continuation_not_comparable"
    if a.get("provider_calls") == 0 or b.get("provider_calls") == 0:
        return "initial_matched_only"
    if a.get("stop_reason") != b.get("stop_reason"):
        return "initial_matched_only"
    return "operationally_comparable"


def run_pilot(client: OpenAICompatibleClient) -> dict[str, Any]:
    conditions, scenarios = contract_module.default_contract()
    adapter = contract_module.MatchedContractAdapter(conditions, scenarios)
    adapter.validate_runner_inputs(
        condition_names=CONDITION_ORDER,
        source_ids=("shared-source", "shared-source"),
        context_ids=("shared-context", "shared-context"),
        max_turns=MAX_TURNS,
    )
    rows = []
    for index, spec in enumerate(base.CASES[:2]):
        scenario = scenarios[index]
        result_a = run_condition(client, spec, "A", scenario=scenario, adapter=adapter)
        result_b = run_condition(client, spec, "B", scenario=scenario, adapter=adapter)
        rows.append(
            {
                "case_alias": f"case-{index}",
                "A": result_a,
                "B": result_b,
                "pair_comparability": _pair_comparability(result_a, result_b),
                "semantic_oracle": "none",
            }
        )
    return {
        "record_type": "pr53_redaction_safe_bounded_live_pilot",
        "pilot_version": PILOT_VERSION,
        "source_sha": SOURCE_SHA,
        "provider_protocol_version": PROVIDER_PROTOCOL_VERSION,
        "condition_order": list(CONDITION_ORDER),
        "max_cases": 2,
        "max_turns": MAX_TURNS,
        "cases": rows,
        "aggregate_verdict": "not_comparable",
        "semantic_identity": "not_evaluated",
        "production_admission_changed": False,
        "semantic_adjudication_receipt_created": False,
        "provider_payloads_recorded": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-digest", default=None)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    args = parser.parse_args()
    client = OpenAICompatibleClient(
        ProviderProfile(
            base_url=args.endpoint,
            model=args.model,
            max_output_tokens=args.max_output_tokens,
            temperature=0.0,
            disable_thinking=True,
            timeout_seconds=90,
        )
    )
    payload = run_pilot(client)
    payload.update(
        {
            "run_id": args.run_id,
            "model": Path(args.model).name,
            "model_artifact_digest": args.model_digest,
            "backend": "llama.cpp OpenAI-compatible /v1",
            "endpoint": "http://127.0.0.1:8080",
            "sampling": {
                "temperature": 0,
                "thinking_enabled": False,
                "max_output_tokens": args.max_output_tokens,
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
