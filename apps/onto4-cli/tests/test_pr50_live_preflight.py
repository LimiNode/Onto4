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

    public = _SCRIPT._public_case(raw, alias="case-0")
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
