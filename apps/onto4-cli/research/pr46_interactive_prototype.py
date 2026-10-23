"""Run one redaction-safe, one-turn interactive Onto4 prototype.

The prototype exercises the existing host-controlled loop against an actual
OpenAI-compatible endpoint:

    interpretation -> formalization/assessment -> clarification ->
    refinement -> reassessment

Only safe lifecycle and semantic status metadata are written.  Provider JSON,
credentials, source text and the free-form answer are never written to the
artifact.  This is an integration experiment, not production admission and
not a semantic adjudication receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

from onto4.pipeline import ModelClarificationPolicy, run_interactive_dialogue
from onto4.pipeline.loaders import load_context
from onto4.providers import (
    EndpointAuthKind,
    OpenAICompatibleClient,
    OpenAICompatibleFormalizationProvider,
    OpenAICompatibleInterpretationProvider,
    ProviderProfile,
    ProviderStageEvent,
    InterpretationRequest,
)
from onto4.reasoning import FixtureClarificationPolicy


CASE_ID = "genome-identity-interactive-one-turn"
SOURCE_TEXT = "Does sharing a genome make two people one person?"
ANSWER = "I mean numerical identity: they are one and the same individual."
FROZEN_ANSWER_ID = "genome-identity-numerical-first-turn"

_SAFE_STAGES = frozenset({"interpretation", "formalization", "refinement"})
_SAFE_PHASES = frozenset(
    {"started", "response_received", "json_valid", "json_invalid", "completed", "failed"}
)
_SAFE_FINISH_REASONS = frozenset(
    {"stop", "length", "tool_calls", "function_call", "content_filter", "unknown"}
)
_SAFE_FAILURE_DETAILS = frozenset({"transport", "schema", "unexpected"})


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def _safe_model(model: str) -> str:
    if "\\" in model:
        return PureWindowsPath(model).name
    return Path(model).name if "/" in model else model


def _safe_answer_metadata(answer: str) -> dict[str, Any]:
    if answer == ANSWER:
        return {"fixture_id": FROZEN_ANSWER_ID}
    return {"fingerprint_recorded": False}


def _event_payload(event: ProviderStageEvent) -> dict[str, Any]:
    stage = event.stage if isinstance(event.stage, str) and event.stage in _SAFE_STAGES else "unknown"
    phase = event.phase if isinstance(event.phase, str) and event.phase in _SAFE_PHASES else "unknown"
    detail = ""
    raw_detail = event.detail if isinstance(event.detail, str) else ""
    if phase == "response_received":
        finish_reason = "unknown"
        completion_tokens: int | None = None
        if raw_detail.startswith("finish_reason="):
            raw_finish, *raw_usage = raw_detail.split(", ", 1)
            candidate = raw_finish.removeprefix("finish_reason=")
            if candidate in _SAFE_FINISH_REASONS:
                finish_reason = candidate
            if raw_usage and raw_usage[0].startswith("completion_tokens="):
                raw_tokens = raw_usage[0].removeprefix("completion_tokens=")
                if raw_tokens.isdigit():
                    completion_tokens = int(raw_tokens)
        detail = f"finish_reason={finish_reason}"
        if completion_tokens is not None:
            detail += f", completion_tokens={completion_tokens}"
    elif phase == "completed" and raw_detail == "schema_valid":
        detail = "schema_valid"
    elif phase == "failed" and raw_detail in _SAFE_FAILURE_DETAILS:
        detail = raw_detail
    elapsed = event.elapsed_seconds
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or not math.isfinite(elapsed):
        elapsed = 0.0
    elapsed = max(0.0, min(float(elapsed), 86_400.0))
    return {
        "stage": stage,
        "phase": phase,
        "elapsed_seconds": round(elapsed, 3),
        "detail": detail,
    }


def run_prototype(
    *,
    endpoint: str,
    model: str,
    context_path: Path,
    answer: str = ANSWER,
    timeout: float = 120.0,
    max_output_tokens: int = 768,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    prompts: list[str] = []

    def trace(event: ProviderStageEvent) -> None:
        events.append(_event_payload(event))

    profile = ProviderProfile(
        base_url=endpoint,
        model=model,
        auth=EndpointAuthKind.None_,
        timeout_seconds=timeout,
        max_output_tokens=max_output_tokens,
        disable_thinking=True,
        temperature=0.0,
    )
    client = OpenAICompatibleClient(profile)
    context = load_context(context_path)
    contexts = {context_path.stem: context}
    interpretation_provider = OpenAICompatibleInterpretationProvider(client, trace=trace)
    formalization_provider = OpenAICompatibleFormalizationProvider(
        client,
        context_ids=tuple(contexts),
        trace=trace,
    )
    request = InterpretationRequest(SOURCE_TEXT)
    answer_used = False

    def input_fn(_: str) -> str:
        nonlocal answer_used
        if answer_used:
            raise EOFError("The one-turn prototype received a second clarification request.")
        answer_used = True
        return answer

    dialogue = run_interactive_dialogue(
        request,
        interpretation_provider=interpretation_provider,
        refinement_provider=interpretation_provider,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=ModelClarificationPolicy(
            FixtureClarificationPolicy(), interpretation_provider
        ),
        input_fn=input_fn,
        output_fn=prompts.append,
        max_turns=1,
    )
    assessment = dialogue.session.assessment
    if assessment is None:
        raise ValueError("Prototype ended without a current assessment.")
    ask_result = assessment.ask_result
    progress = [
        {
            "question_id": entry.question_id,
            "kind": entry.kind.value,
            "new_item_count": len(entry.new_item_ids),
            "new_semantic_signature_count": len(entry.new_semantic_signatures),
            "refinement_operations": list(entry.refinement_operations),
            "refinement_effects": list(entry.refinement_effects),
            "refinement_committed": entry.refinement_committed,
        }
        for entry in dialogue.progress.entries
    ]
    return {
        "record_type": "pr46_redaction_safe_interactive_prototype",
        "experiment_version": 1,
        "case_id": CASE_ID,
        "source": {
            "source_digest": _digest(SOURCE_TEXT),
            "source_length": len(SOURCE_TEXT),
            "context_id": context_path.stem,
        },
        "answer": _safe_answer_metadata(answer),
        "provider": {
            "endpoint": _safe_endpoint(endpoint),
            "model": _safe_model(model),
            "temperature": 0.0,
            "max_output_tokens": max_output_tokens,
            "thinking_enabled": False,
        },
        "stages": events,
        "clarification_prompts_emitted": len(prompts),
        "turns": dialogue.turns,
        "stop_reason": dialogue.stop_reason,
        "final": {
            "interpretation_id": ask_result.interpretation.id,
            "landscape": ask_result.landscape.status.value,
            "disposition": ask_result.disposition.value,
            "reason": ask_result.reason,
            "assessment_count": len(ask_result.assessments),
            "assessment_states": [item.result.state.value for item in ask_result.assessments],
            "assessment_verdicts": [
                item.result.verdict.value if item.result.verdict is not None else None
                for item in ask_result.assessments
            ],
        },
        "progress": progress,
        "model_run_started": True,
        "provider_payloads_recorded": False,
        "production_admission_changed": False,
        "semantic_adjudication_receipt_created": False,
        "historical_pr40_semantic_identity": "not_evaluated",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--answer", default=ANSWER)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-output-tokens", type=int, default=768)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = run_prototype(
        endpoint=args.endpoint,
        model=args.model,
        context_path=args.context,
        answer=args.answer,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
