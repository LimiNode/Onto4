import importlib.util
import json
from pathlib import Path
import sys


_SCRIPT_PATH = Path(__file__).parents[1] / "research" / "pr50_live_preflight.py"
_SPEC = importlib.util.spec_from_file_location("pr50_live_preflight", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCRIPT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCRIPT
_SPEC.loader.exec_module(_SCRIPT)


def test_public_case_redacts_targets_and_requires_both_conditions():
    raw = {
        "question_kind": "Meaning",
        "question_target_ids": ["private-target"],
        "cells": [
            {
                "condition": "full_snapshot",
                "provider_successor_valid": True,
                "transition_provenance_valid": True,
                "target_present_in_successor": False,
                "binding": {
                    "schema": "valid",
                    "catalog": "valid",
                    "lineage": "valid",
                    "transition": "valid",
                    "semantic_identity": "not_comparable",
                    "structurally_admissible": False,
                    "errors": [],
                },
            },
            {
                "condition": "explicit_binding",
                "provider_successor_valid": True,
                "transition_provenance_valid": True,
                "target_present_in_successor": True,
                "binding": {
                    "schema": "valid",
                    "catalog": "valid",
                    "lineage": "valid",
                    "transition": "valid",
                    "semantic_identity": "unverified",
                    "structurally_admissible": True,
                    "errors": [],
                },
            },
        ],
    }

    contract = {
        "same_initial_snapshot": True,
        "same_question": True,
        "same_answer": True,
        "same_case_context": True,
        "contract_digest": "a" * 64,
        "status": "host_verified",
    }
    public = _SCRIPT._public_case(raw, alias="case-0", host_contract=contract)
    serialized = json.dumps(public, ensure_ascii=False)

    assert public["host_input_contract"]["status"] == "host_verified"
    assert public["comparison_verdict"] == "not_comparable"
    assert public["question_target_count"] == 1
    assert "private-target" not in serialized


def test_public_case_is_not_host_verified_when_a_condition_is_missing():
    raw = {
        "question_kind": "Meaning",
        "question_target_ids": ["private-target"],
        "cells": [
            {
                "condition": "full_snapshot",
                "provider_successor_valid": False,
                "transition_provenance_valid": False,
            }
        ],
    }

    public = _SCRIPT._public_case(raw, alias="case-0")

    assert public["host_input_contract"]["status"] == "not_verified"
    assert public["comparison_verdict"] == "not_comparable"


def test_host_contract_mismatch_fails_closed():
    left = {
        "initial_snapshot_digest": "a",
        "question_digest": "b",
        "answer_obligation_digest": "c",
        "context_binding_digest": "d",
        "contract_digest": "e",
    }
    right = {**left, "question_digest": "changed"}

    verified = _SCRIPT._verify_host_input_contract(left, {**left})
    rejected = _SCRIPT._verify_host_input_contract(left, right)

    assert verified["status"] == "host_verified"
    assert rejected["status"] == "not_verified"
    assert rejected["contract_digest"] is None


def test_host_contract_same_object_is_not_independent_evidence():
    snapshot = {
        "initial_snapshot_digest": "a",
        "question_digest": "b",
        "answer_obligation_digest": "c",
        "context_binding_digest": "d",
        "contract_digest": "e",
    }
    assert _SCRIPT._verify_host_input_contract(snapshot, snapshot)["status"] == "not_verified"


def test_condition_cell_status_rejects_missing_and_duplicate_cells():
    full = {"condition": "full_snapshot"}
    explicit = {"condition": "explicit_binding"}
    assert _SCRIPT._condition_cell_status((full, explicit)) == "host_verified"
    assert _SCRIPT._condition_cell_status((full,)) == "not_verified"
    assert _SCRIPT._condition_cell_status((full, explicit, explicit)) == "not_verified"


def test_public_cell_allowlist_redacts_private_diagnostics_and_paths():
    cell = {
        "condition": "explicit_binding",
        "provider_successor_valid": False,
        "transition_provenance_valid": False,
        "target_present_in_successor": None,
        "outcome": "PRIVATE_TARGET_ID / C:\\secret\\prompt.txt",
        "detail_code": "PRIVATE_ANSWER",
        "binding": {
            "schema": "invalid",
            "catalog": "invalid",
            "lineage": "invalid",
            "transition": "invalid",
            "semantic_identity": "unverified",
            "structurally_admissible": False,
            "errors": ["PRIVATE_TARGET_ID", "private answer text"],
        },
    }

    serialized = json.dumps(_SCRIPT._public_cell(cell), ensure_ascii=False)

    assert "PRIVATE_TARGET_ID" not in serialized
    assert "PRIVATE_ANSWER" not in serialized
    assert "secret" not in serialized
    assert "binding_error" in serialized


def test_safe_model_strips_windows_and_posix_paths():
    assert _SCRIPT._safe_model(r"F:\\AI\\models\\bonsai\\model.gguf") == "model.gguf"
    assert _SCRIPT._safe_model("/srv/models/model.gguf") == "model.gguf"


def test_committed_preflight_artifact_is_redaction_safe_and_non_semantic():
    artifact_path = (
        Path(__file__).parents[3]
        / "docs"
        / "reports"
        / "pr50-live-preflight-20261025.json"
    )
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["record_type"] == "pr50_redaction_safe_live_paired_preflight"
    assert payload["aggregate_verdict"] == "not_comparable"
    assert payload["semantic_identity"] == "not_evaluated"
    assert payload["model_artifact_digest"] is None
    assert len(payload["cases"]) == 1
    assert "ambiguity-genome" not in serialized
    assert "numerical identity" not in serialized
