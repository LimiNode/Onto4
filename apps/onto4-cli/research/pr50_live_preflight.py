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
import re
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
PREFLIGHT_VERSION = 2
CONDITION_ORDER = ("full_snapshot", "explicit_binding")
REUSED_PR40_RUNNER_REVISION = "d969338ee040e304e4dc1afb0f3aa1a373604967"

_SAFE_CHECK_VALUES = frozenset(
    {"valid", "invalid", "unverified", "not_applicable", "unknown"}
)
_SAFE_SEMANTIC_VALUES = frozenset(
    {"verified", "unverified", "not_comparable", "unknown"}
)
_SAFE_ERROR_CODES = frozenset(
    {
        "binding_error",
        "schema_error",
        "catalog_error",
        "lineage_error",
        "transition_error",
        "target_error",
        "provider_error",
    }
)


def _safe_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def _safe_model(model: str) -> str:
    # ``Path`` follows the host OS semantics; the endpoint may report a path
    # created on another OS.  Split both separators and never publish a drive
    # prefix or parent directory.
    return re.split(r"[\\/]", model)[-1] or "unknown-model"


def _prompt_hash() -> str:
    material = (
        base.EXPLICIT_BINDING_SYSTEM_PROMPT
        + "\n"
        + base.EXPLICIT_BINDING_PROMPT_TEMPLATE
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _digest(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _host_input_contract(
    spec: base.CaseSpec,
    initial: base.InterpretationSpace,
    question: base.ClarificationQuestion,
    catalog: base.SemanticTargetCatalog,
) -> dict[str, str]:
    """Create only digests for the host-owned common input contract."""

    initial_digest = _digest(base._projection(initial))
    question_digest = _digest(
        {
            "kind": question.kind.value,
            "target_ids": tuple(question.target_ids),
            "text": question.text,
        }
    )
    answer_digest = _digest({"answer": spec.answer})
    context_digest = _digest(
        {
            "case_id": spec.case_id,
            "target_kind": spec.target_kind.value,
            "catalog_version": catalog.version,
            "catalog": {
                key: {"kind": target.kind, "description": target.description}
                for key, target in sorted(catalog.targets.items())
            },
        }
    )
    contract_digest = _digest(
        {
            "initial": initial_digest,
            "question": question_digest,
            "answer": answer_digest,
            "context": context_digest,
        }
    )
    return {
        "initial_snapshot_digest": initial_digest,
        "question_digest": question_digest,
        "answer_obligation_digest": answer_digest,
        "context_binding_digest": context_digest,
        "contract_digest": contract_digest,
    }


def _verify_host_input_contract(
    left: Mapping[str, str] | None,
    right: Mapping[str, str] | None,
) -> dict[str, Any]:
    fields = (
        "initial_snapshot_digest",
        "question_digest",
        "answer_obligation_digest",
        "context_binding_digest",
        "contract_digest",
    )
    equal = (
        left is not None
        and right is not None
        and all(left.get(field) == right.get(field) for field in fields)
    )
    return {
        "same_initial_snapshot": bool(equal and left.get(fields[0]) == right.get(fields[0])),
        "same_question": bool(equal and left.get(fields[1]) == right.get(fields[1])),
        "same_answer": bool(equal and left.get(fields[2]) == right.get(fields[2])),
        "same_case_context": bool(equal and left.get(fields[3]) == right.get(fields[3])),
        "contract_digest": left.get("contract_digest") if equal else None,
        "status": "host_verified" if equal else "not_verified",
    }


def _safe_error_code(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "provider_error"
    lowered = value.lower()
    if "schema" in lowered or "claim" in lowered:
        return "schema_error"
    if "catalog" in lowered or "kind" in lowered or "target" in lowered:
        return "target_error"
    if "lineage" in lowered or "snapshot" in lowered:
        return "lineage_error"
    if "transition" in lowered:
        return "transition_error"
    return "binding_error"


def _safe_outcome_code(value: Any) -> str:
    if not isinstance(value, str):
        return "provider_error"
    lowered = value.lower()
    if "schema" in lowered:
        return "schema_error"
    if "transport" in lowered or "timeout" in lowered:
        return "transport_error"
    return "provider_error"


def _public_cell(cell: Mapping[str, Any]) -> dict[str, Any]:
    """Project a PR40 cell without target ids or model-controlled content."""

    binding = cell.get("binding")
    result: dict[str, Any] = {
        "condition": cell.get("condition"),
        "provider_successor_valid": cell.get("provider_successor_valid"),
        "transition_provenance_valid": cell.get("transition_provenance_valid"),
        "target_present_in_successor": cell.get("target_present_in_successor"),
        "binding_claim_mode": (
            "no_binding_by_protocol"
            if cell.get("condition") == "full_snapshot"
            else "provider_binding_claim"
        ),
    }
    if isinstance(binding, Mapping):
        errors = binding.get("errors")
        safe_errors = []
        if isinstance(errors, (list, tuple)):
            safe_errors = sorted(
                {
                    code
                    for code in (_safe_error_code(item) for item in errors)
                    if code in _SAFE_ERROR_CODES
                }
            )
        safe_checks = {
            key: binding.get(key)
            if binding.get(key) in _SAFE_CHECK_VALUES
            else "unknown"
            for key in ("schema", "catalog", "lineage", "transition")
        }
        semantic_identity = binding.get("semantic_identity")
        result["binding"] = {
            **safe_checks,
            "semantic_identity": (
                semantic_identity
                if semantic_identity in _SAFE_SEMANTIC_VALUES
                else "unknown"
            ),
            "structurally_admissible": bool(binding.get("structurally_admissible")),
            "error_codes": safe_errors,
        }
    else:
        result["outcome"] = _safe_outcome_code(cell.get("outcome"))
        result["detail_code"] = _safe_outcome_code(cell.get("detail_code"))
    return result


def _public_case(
    raw: Mapping[str, Any],
    *,
    alias: str,
    host_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cells = tuple(raw.get("cells", ()))
    by_condition = {cell.get("condition"): cell for cell in cells}
    contract = dict(host_contract or {})
    return {
        "case_alias": alias,
        "question_kind": raw.get("question_kind"),
        "question_target_count": len(raw.get("question_target_ids", ())),
        "host_input_contract": contract
        if contract
        else {
            "same_initial_snapshot": False,
            "same_question": False,
            "same_answer": False,
            "same_case_context": False,
            "contract_digest": None,
            "status": "not_verified",
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
        _run_public_case(client, case, alias=f"case-{index}")
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


def _run_public_case(
    client: OpenAICompatibleClient,
    spec: base.CaseSpec,
    *,
    alias: str,
) -> dict[str, Any]:
    """Run both protocol arms from one immutable host-owned input."""

    initial = base._initial(spec)
    question = base._question(spec)
    catalog = base.CATALOGS[spec.case_id]
    contract = _host_input_contract(spec, initial, question, catalog)
    cells: list[dict[str, Any]] = []
    for condition, runner in (
        ("full_snapshot", base._full_snapshot),
        ("explicit_binding", base._explicit_binding),
    ):
        try:
            successor, evaluation = runner(client, spec, initial, question, catalog)
            cells.append(
                {
                    "condition": condition,
                    "provider_successor_valid": True,
                    "transition_provenance_valid": True,
                    "target_present_in_successor": base._target_present(successor, spec.target_id),
                    "binding": base._evaluation_payload(evaluation),
                }
            )
        except Exception as exc:
            cells.append(
                {
                    "condition": condition,
                    "provider_successor_valid": False,
                    "transition_provenance_valid": False,
                    "target_present_in_successor": None,
                    "outcome": getattr(exc, "code", type(exc).__name__),
                    "detail_code": getattr(exc, "code", type(exc).__name__),
                }
            )
    raw = {
        "question_kind": question.kind.value,
        "question_target_ids": question.target_ids,
        "cells": cells,
    }
    return _public_case(raw, alias=alias, host_contract=_verify_host_input_contract(contract, contract))


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
            "reused_pr40_runner_revision": REUSED_PR40_RUNNER_REVISION,
            "preflight_type": "provider_protocol",
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
