import importlib.util
from pathlib import Path
import sys


_SCRIPT_PATH = Path(__file__).parents[1] / "research" / "pr46_interactive_prototype.py"
_SPEC = importlib.util.spec_from_file_location("pr46_interactive_prototype", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCRIPT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCRIPT
_SPEC.loader.exec_module(_SCRIPT)


def test_redaction_helpers_do_not_preserve_endpoint_credentials_or_paths():
    assert _SCRIPT._safe_endpoint("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080"
    assert _SCRIPT._safe_endpoint("https://user:secret@example.test/v1") == (
        "https://example.test"
    )
    assert _SCRIPT._safe_model(
        r"F:\AI\models\bonsai2-27b\Ternary-Bonsai-2-27B-PQ2_0.gguf"
    ) == "Ternary-Bonsai-2-27B-PQ2_0.gguf"


def test_event_payload_uses_closed_metadata_allowlist():
    safe = _SCRIPT._event_payload(
        _SCRIPT.ProviderStageEvent(
            "interpretation",
            "response_received",
            1.25,
            "finish_reason=PRIVATE_MODEL_OUTPUT, secret=do-not-publish",
        )
    )
    assert safe["detail"] == "finish_reason=unknown"

    failure = _SCRIPT._event_payload(
        _SCRIPT.ProviderStageEvent(
            "unexpected-private-stage",
            "private-phase",
            2.0,
            "PRIVATE_MODEL_OUTPUT",
        )
    )
    assert failure == {
        "stage": "unknown",
        "phase": "unknown",
        "elapsed_seconds": 2.0,
        "detail": "",
    }
    malformed = _SCRIPT._event_payload(
        _SCRIPT.ProviderStageEvent([], {}, float("nan"), None)
    )
    assert malformed == {
        "stage": "unknown",
        "phase": "unknown",
        "elapsed_seconds": 0.0,
        "detail": "",
    }


def test_arbitrary_answer_has_no_public_fingerprint():
    assert _SCRIPT._safe_answer_metadata("private user answer") == {
        "fingerprint_recorded": False
    }


def test_published_prototype_artifact_is_redaction_safe_and_bounded():
    import json

    artifact_path = Path(__file__).parents[3] / "docs" / "reports" / "pr46-interactive-prototype.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["record_type"] == "pr46_redaction_safe_interactive_prototype"
    assert artifact["turns"] == 1
    assert artifact["stop_reason"] == "max_turns_reached"
    assert artifact["final"]["disposition"] == "AskClarification"
    assert artifact["final"]["assessment_verdicts"] == ["U", "U"]
    assert artifact["progress"][0]["kind"] == "structural_resolution"
    assert artifact["provider_payloads_recorded"] is False
    assert artifact["production_admission_changed"] is False
    assert artifact["semantic_adjudication_receipt_created"] is False
    serialized = json.dumps(artifact, ensure_ascii=False)
    assert _SCRIPT.SOURCE_TEXT not in serialized
    assert _SCRIPT.ANSWER not in serialized
    assert r"F:\AI\models\bonsai2-27b" not in serialized
    assert artifact["answer"] == {"fixture_id": _SCRIPT.FROZEN_ANSWER_ID}
