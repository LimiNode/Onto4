"""Run one redaction-safe live paired preflight for the PR #50 pilot.

The preflight deliberately uses one host-grounded case and one answer in both
conditions.  It reuses the PR40 schema/binding runner, but publishes only
condition outcomes and validation states.  It never publishes prompts,
answers, provider payloads or target identifiers, and it never creates a
semantic adjudication receipt or changes production admission.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping
from urllib.parse import urlsplit

from onto4.providers import OpenAICompatibleClient, ProviderProfile


_BASE_SPEC = importlib.util.spec_from_file_location(
    "pr40_semantic_binding_runner_for_pr50",
    Path(__file__).with_name("pr40_semantic_binding_runner.py"),
)
assert _BASE_SPEC is not None and _BASE_SPEC.loader is not None
base = importlib.util.module_from_spec(_BASE_SPEC)
sys.modules[_BASE_SPEC.name] = base
_BASE_SPEC.loader.exec_module(base)


SOURCE_SHA = "e897eaf0ed3450de30cefcfe34b011d7b4936093"
PREFLIGHT_VERSION = 1
CONDITION_ORDER = ("full_snapshot", "explicit_binding")


def _safe_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def _safe_model(model: str) -> str:
    return Path(model).name if "/" in model or "\\" in model else model


def _prompt_hash() -> str:
    material = (
        base.EXPLICIT_BINDING_SYSTEM_PROMPT
        + "\n"
        + base.EXPLICIT_BINDING_PROMPT_TEMPLATE
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _public_cell(cell: Mapping[str, Any]) -> dict[str, Any]:
    """Project a PR40 cell without target ids or model-controlled content."""

    binding = cell.get("binding")
    result: dict[str, Any] = {
        "condition": cell.get("condition"),
        "provider_successor_valid": cell.get("provider_successor_valid"),
        "transition_provenance_valid": cell.get("transition_provenance_valid"),
        "target_present_in_successor": cell.get("target_present_in_successor"),
    }
    if isinstance(binding, Mapping):
        result["binding"] = {
            key: binding.get(key)
            for key in (
                "schema",
                "catalog",
                "lineage",
                "transition",
                "semantic_identity",
                "structurally_admissible",
                "errors",
            )
        }
    else:
        result["outcome"] = cell.get("outcome")
        result["detail_code"] = cell.get("detail_code")
    return result


def _public_case(raw: Mapping[str, Any], *, alias: str) -> dict[str, Any]:
    cells = tuple(raw.get("cells", ()))
    by_condition = {cell.get("condition"): cell for cell in cells}
    same_input = all(
        bool(by_condition.get(condition))
        for condition in CONDITION_ORDER
    )
    return {
        "case_alias": alias,
        "question_kind": raw.get("question_kind"),
        "question_target_count": len(raw.get("question_target_ids", ())),
        "host_input_contract": {
            "same_initial_snapshot": same_input,
            "same_question": same_input,
            "same_answer": same_input,
            "status": "host_verified" if same_input else "not_verified",
        },
        "comparison_verdict": "not_comparable",
        "semantic_oracle": "none",
        "cells": [_public_cell(by_condition.get(condition, {})) for condition in CONDITION_ORDER],
    }


def run_preflight(
    client: OpenAICompatibleClient,
    *,
    cases: tuple[base.CaseSpec, ...] = (base.CASES[0],),
) -> dict[str, Any]:
    rows = [
        _public_case(base.run_case(client, case), alias=f"case-{index}")
        for index, case in enumerate(cases)
    ]
    return {
        "record_type": "pr50_redaction_safe_live_paired_preflight",
        "experiment_version": PREFLIGHT_VERSION,
        "conditions": {
            "full_snapshot": "full_snapshot",
            "explicit_binding": "explicit_binding",
        },
        "condition_order": list(CONDITION_ORDER),
        "max_turns": 1,
        "cases": rows,
        "aggregate_verdict": "not_comparable",
        "semantic_identity": "not_evaluated",
        "host_workflow_admission": "not_evaluated",
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
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    args = parser.parse_args()
    profile = ProviderProfile(
        base_url=args.endpoint,
        model=args.model,
        max_output_tokens=args.max_output_tokens,
        temperature=0,
        disable_thinking=True,
        timeout_seconds=90,
    )
    client = OpenAICompatibleClient(profile)
    payload = run_preflight(client)
    payload.update(
        {
            "run_id": args.run_id,
            "source_sha": SOURCE_SHA,
            "runner_source_sha": SOURCE_SHA,
            "model": _safe_model(args.model),
            "model_artifact_digest": args.model_digest,
            "backend": "llama.cpp OpenAI-compatible /v1",
            "endpoint": _safe_endpoint(args.endpoint),
            "sampling": {
                "temperature": 0,
                "thinking_enabled": False,
                "max_output_tokens": args.max_output_tokens,
            },
            "prompt_version": base.PROMPT_VERSION,
            "prompt_hash": _prompt_hash(),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
