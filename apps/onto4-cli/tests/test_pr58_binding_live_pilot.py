import importlib.util
import json
from pathlib import Path
import sys


_PATH = Path(__file__).parents[1] / "research" / "pr58_binding_live_pilot.py"
_SPEC = importlib.util.spec_from_file_location("pr58_binding_live_pilot", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _interpretation(source: str, target_id: str) -> dict:
    return {
        "source_text": source,
        "conceptual_depth": "philosophical",
        "ambiguities": [
            {"term": "host target", "description": "bounded fixture", "target_id": target_id}
        ],
        "presuppositions": [],
        "ontologies": [],
        "readings": [],
    }


class _FakeClient:
    class _Profile:
        temperature = 0
        max_output_tokens = 1024
        disable_thinking = True

    profile = _Profile()

    def __init__(self):
        self.calls = []

    def complete(self, messages, *, response_format):
        self.calls.append(messages)
        user = messages[-1]["content"]
        source = (
            "Does sharing a genome make two people one person?"
            if "genome" in user
            else "Does the sequence have an intrinsic present?"
        )
        target_id = "ambiguity-genome" if "genome" in user else "ambiguity-present"
        successor = _interpretation(source, target_id)
        if "binding_claim" in user:
            previous = "genome-identity-bounded-host-initial" if "genome" in user else "intrinsic-time-bounded-host-initial"
            current = "genome-identity-bounded-minimal-successor" if "genome" in user else "intrinsic-time-bounded-minimal-successor"
            content = json.dumps(
                {
                    "successor": successor,
                    "binding_claim": {
                        "relation": "preserve",
                        "target_id": target_id,
                        "target_kind": "Meaning",
                        "source_target_id": target_id,
                        "previous_snapshot_id": previous,
                        "current_snapshot_id": current,
                    },
                }
            )
        else:
            content = json.dumps(successor)
        return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}


def test_pilot_is_bounded_to_six_calls_and_keeps_semantics_unverified():
    client = _FakeClient()
    result = _MODULE.run_pilot(client)
    assert len(client.calls) == 6
    assert len(result["cases"]) == 2
    assert all(len(case["cells"]) == 3 for case in result["cases"])
    assert all(cell["model_calls"] == 1 for case in result["cases"] for cell in case["cells"])
    assert result["semantic_correctness"] == "not_evaluated"
    assert result["aggregate_verdict"] == "not_comparable"


def test_pilot_output_is_redaction_safe_and_reproducible():
    client = _FakeClient()
    result = _MODULE.run_pilot(client)
    serialized = json.dumps(result, ensure_ascii=False)
    assert result["source_sha"] == "8450d2ffe4bd09642426d8777f99b1eb0f52e0a1"
    assert result["sampling_settings"]["temperature"] == 0
    assert "ambiguity-genome" not in serialized
    assert "identity_and_genome" not in serialized
    assert "numerical identity" not in serialized
    assert "provider_payloads_recorded" in serialized
    assert '"source_text"' not in serialized


def test_cell_records_provider_failure_without_claiming_semantic_failure():
    class Broken(_FakeClient):
        def complete(self, messages, *, response_format):
            self.calls.append(messages)
            raise RuntimeError("transport failed at local endpoint")

    spec = _MODULE.base.CASES[0]
    row = _MODULE._cell(Broken(), spec, "A")
    assert row["model_calls"] == 1
    assert row["provider_successor_valid"] is False
    assert row["semantic_correctness"] == "not_evaluated"
    assert row["literal_target_preserved"] is None
