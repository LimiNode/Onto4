"""Run one bounded three-protocol provider target-binding pilot."""

from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import sys
import time
from typing import Any

from onto4.pipeline.semantic_binding import BindingTransition, evaluate_binding_claim
from onto4.providers import OpenAICompatibleClient, OpenAICompatibleInterpretationProvider, ProviderProfile
from onto4.providers.openai_adapters import _parse_interpretation, _response_json
from onto4.providers.protocols import InterpretationRequest


_BASE_SPEC = importlib.util.spec_from_file_location(
    "pr40_semantic_binding_runner_for_pr58",
    Path(__file__).with_name("pr40_semantic_binding_runner.py"),
)
assert _BASE_SPEC is not None and _BASE_SPEC.loader is not None
base = importlib.util.module_from_spec(_BASE_SPEC)
sys.modules[_BASE_SPEC.name] = base
_BASE_SPEC.loader.exec_module(base)

_PROTOCOL_SPEC = importlib.util.spec_from_file_location(
    "pr56_target_binding_protocol_for_pr58",
    Path(__file__).with_name("pr56_target_binding_protocol.py"),
)
assert _PROTOCOL_SPEC is not None and _PROTOCOL_SPEC.loader is not None
protocol = importlib.util.module_from_spec(_PROTOCOL_SPEC)
sys.modules[_PROTOCOL_SPEC.name] = protocol
_PROTOCOL_SPEC.loader.exec_module(protocol)


# Exact source revision for reproducibility; this pilot is deliberately tied to
# the reviewed conformance gate rather than to a moving branch label.
SOURCE_SHA = "0463972"
HISTORICAL_PILOT_VERSION = "pr58-binding-live-pilot-v1"
PILOT_VERSION = "pr58-binding-live-pilot-v2-runner"
CONDITIONS = ("A", "B", "C")
_EXPECTED_SETTINGS = {"temperature": 0, "max_output_tokens": 1024, "disable_thinking": True}
_FROZEN_SCENARIO_DIGESTS = {
    "genome-identity-bounded": "3eb82b0c0380b13c3398817fd40ffe4ace2addc6a2d89cf80aaf047ee664ffb6",
    "intrinsic-time-bounded": "cf23933e575a7b391c0c93cc7ce30961873abe959cecb79abfa177507941b5c8",
}

_MINIMAL_SYSTEM = "Return only the requested JSON object."
_MINIMAL_TEMPLATE = (
    "Refine this host interpretation after the answer. Return exactly successor "
    "and binding_claim. The successor has source_text, conceptual_depth, "
    "ambiguities, presuppositions, ontologies and readings. The binding_claim "
    "has relation, target_id, target_kind, source_target_id, previous_snapshot_id "
    "and current_snapshot_id. Host target id: {target_id}; target kind: {kind}; "
    "previous snapshot: {previous}; current snapshot: {current}; answer: {answer}."
)


def _safe_error(exc: Exception) -> str:
    value = str(getattr(exc, "code", type(exc).__name__)).lower()
    if "schema" in value or "json" in value:
        return "schema_failure"
    if "timeout" in value or "transport" in value or "connection" in value:
        return "transport_failure"
    return "provider_failure"


class _CallCountingClient:
    """Host-side counter; provider payloads remain inaccessible to receipts."""

    def __init__(self, client: OpenAICompatibleClient) -> None:
        self.client = client
        self.profile = client.profile
        self.actual_calls = 0
        self.completed_calls = 0

    def complete(self, messages: Any, *, response_format: Any) -> Any:
        self.actual_calls += 1
        result = self.client.complete(messages, response_format=response_format)
        self.completed_calls += 1
        return result


def _scenario_for_spec(spec: base.CaseSpec) -> Any:
    _, scenarios = protocol.default_protocol()
    matches = [scenario for scenario in scenarios if scenario.case_id == spec.case_id]
    if len(matches) != 1:
        raise ValueError("Frozen scenario case_id does not match the selected case.")
    return matches[0]


def _condition_for_name(name: str) -> Any:
    conditions, _ = protocol.default_protocol()
    matches = [condition for condition in conditions if condition.name == name]
    if len(matches) != 1:
        raise ValueError("Unknown frozen protocol condition.")
    return matches[0]


def _validate_frozen_invocation(
    spec: base.CaseSpec,
    scenario: Any,
    question: Any,
    condition: Any,
    client: OpenAICompatibleClient,
) -> None:
    if spec.case_id != scenario.case_id:
        raise ValueError("Scenario case_id mismatch.")
    if spec.source_text != scenario.source_text or spec.answer != scenario.answer:
        raise ValueError("Frozen source or answer mismatch.")
    if spec.target_id != scenario.target_id:
        raise ValueError("Frozen target_id mismatch.")
    if question.kind.value != scenario.question_kind or question.target_ids != (scenario.target_id,):
        raise ValueError("Frozen question provenance mismatch.")
    if question.target_family != scenario.target_family:
        raise ValueError("Frozen target family mismatch.")
    if condition.name not in CONDITIONS:
        raise ValueError("Condition is not part of the frozen protocol.")
    settings = {
        "temperature": client.profile.temperature,
        "max_output_tokens": client.profile.max_output_tokens,
        "disable_thinking": client.profile.disable_thinking,
    }
    if settings != _EXPECTED_SETTINGS:
        raise ValueError("Decoding settings do not match the frozen pilot.")
    if protocol.scenario_digest(scenario) != _FROZEN_SCENARIO_DIGESTS.get(scenario.case_id):
        raise ValueError("Frozen scenario digest mismatch.")


def _minimal_binding(
    client: OpenAICompatibleClient,
    spec: base.CaseSpec,
    initial: Any,
    question: Any,
    catalog: Any,
) -> tuple[Any, Any]:
    successor_id = f"{spec.case_id}-minimal-successor"
    prompt = _MINIMAL_TEMPLATE.format(
        target_id=question.target_ids[0],
        kind=question.kind.value,
        previous=initial.id,
        current=successor_id,
        answer=spec.answer,
    )
    payload = _response_json(
        client,
        ({"role": "system", "content": _MINIMAL_SYSTEM}, {"role": "user", "content": prompt}),
        stage="pr58-minimal-target-focused",
    )
    if set(payload) != {"successor", "binding_claim"}:
        raise ValueError("Minimal binding envelope has unexpected fields.")
    parsed = _parse_interpretation(
        payload["successor"],
        InterpretationRequest(initial.source_text, conceptual_depth=initial.conceptual_depth),
    )
    successor = replace(parsed, id=successor_id)
    evaluation = evaluate_binding_claim(
        payload["binding_claim"],
        transition=BindingTransition(initial, successor, question),
        catalog=catalog,
    )
    return successor, evaluation


def _cell(client: OpenAICompatibleClient, spec: base.CaseSpec, condition: str) -> dict[str, Any]:
    initial = base._initial(spec)
    question = base._question(spec)
    scenario = _scenario_for_spec(spec)
    question = replace(question, target_family=scenario.target_family)
    catalog = base.CATALOGS[spec.case_id]
    frozen_condition = _condition_for_name(condition)
    _validate_frozen_invocation(spec, scenario, question, frozen_condition, client)
    counting_client = _CallCountingClient(client)
    started = time.perf_counter()
    try:
        runner = {"A": base._full_snapshot, "B": base._explicit_binding, "C": _minimal_binding}[condition]
        successor, evaluation = runner(counting_client, spec, initial, question, catalog)
        return {
            "condition": condition,
            "attempted_invocations": 1,
            "actual_client_invocation_attempts": counting_client.actual_calls,
            "completed_provider_executions": counting_client.completed_calls,
            "provider_successor_valid": True,
            "schema": evaluation.schema.value,
            "catalog": evaluation.catalog.value,
            "lineage": evaluation.lineage.value,
            "transition": evaluation.transition.value,
            "literal_target_preserved": base._target_present(successor, spec.target_id),
            "semantic_correctness": "not_evaluated",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "condition": condition,
            "attempted_invocations": 1,
            "actual_client_invocation_attempts": counting_client.actual_calls,
            "completed_provider_executions": counting_client.completed_calls,
            "provider_successor_valid": False,
            "failure": _safe_error(exc),
            "literal_target_preserved": None,
            "semantic_correctness": "not_evaluated",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }


def run_pilot(client: OpenAICompatibleClient) -> dict[str, Any]:
    conditions, scenarios = protocol.default_protocol()
    protocol.validate_protocol(conditions, scenarios)
    rows = []
    for index, spec in enumerate(base.CASES[:2]):
        cells = [_cell(client, spec, condition) for condition in CONDITIONS]
        rows.append({
            "case_alias": f"case-{index}",
            "cells": cells,
            "semantic_oracle": "none",
            "semantic_correctness": "not_evaluated",
        })
    return {
        "record_type": "pr58_redaction_safe_binding_live_pilot",
        "pilot_version": PILOT_VERSION,
        "historical_receipt_version": HISTORICAL_PILOT_VERSION,
        "historical_receipt_unchanged": True,
        "source_sha": SOURCE_SHA,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "condition_order": list(CONDITIONS),
        "scenario_order": [scenario.public_alias for scenario in scenarios],
        "max_cases": 2,
        "calls_per_condition_and_case": 1,
        "call_accounting": {
            "attempted": "host client.complete invocations",
            "completed": "client.complete returned a response envelope",
            "provider_side_execution_attested": False,
        },
        "sampling_settings": {
            "temperature": client.profile.temperature,
            "max_output_tokens": client.profile.max_output_tokens,
            "disable_thinking": client.profile.disable_thinking,
        },
        "cases": rows,
        "aggregate_verdict": "not_comparable",
        "semantic_oracle": "none",
        "semantic_correctness": "not_evaluated",
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
    args = parser.parse_args()
    client = OpenAICompatibleClient(ProviderProfile(base_url=args.endpoint, model=args.model, max_output_tokens=1024, temperature=0, disable_thinking=True, timeout_seconds=90))
    payload = run_pilot(client)
    payload.update({"run_id": args.run_id, "model": Path(args.model).name, "model_artifact_digest": args.model_digest, "backend": "llama.cpp OpenAI-compatible /v1", "endpoint": "http://127.0.0.1:8080"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
