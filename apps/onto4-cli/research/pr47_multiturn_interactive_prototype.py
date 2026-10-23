"""Run a bounded, redaction-safe multi-turn interactive prototype.

Unlike the one-turn PR #46 runner, this runner obtains each clarification
answer from ``input()``.  It records only host-owned lifecycle metadata and a
vector of uncertainty observations.  The observations distinguish structural
open targets from ``U`` verdicts; neither is treated as proof of semantic
identity.  This is a research experiment, not production admission and not a
semantic-adjudication receipt.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from onto4.core import AssessmentState, Verdict
from onto4.pipeline import ModelClarificationPolicy, run_interactive_dialogue
from onto4.pipeline.loaders import load_context
from onto4.providers import (
    EndpointAuthKind,
    FormalizationProvider,
    InterpretationProvider,
    InterpretationRequest,
    InterpretationRefinementProvider,
    OpenAICompatibleClient,
    OpenAICompatibleFormalizationProvider,
    OpenAICompatibleInterpretationProvider,
    ProviderProfile,
    ProviderStageEvent,
)
from onto4.reasoning import ClarificationQuestion
from onto4.reasoning import FixtureClarificationPolicy


CASE_ID = "genome-identity-interactive-multiturn"
SOURCE_TEXT = "Does sharing a genome make two people one person?"
_PUBLIC_CASE_ALIAS = "case-0"

_SAFE_STAGES = frozenset({"interpretation", "formalization", "refinement"})
_SAFE_PHASES = frozenset(
    {"started", "response_received", "json_valid", "json_invalid", "completed", "failed"}
)
_SAFE_FINISH_REASONS = frozenset(
    {"stop", "length", "tool_calls", "function_call", "content_filter", "unknown"}
)
_SAFE_FAILURE_DETAILS = frozenset({"transport", "schema", "unexpected"})


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
    return {
        "stage": stage,
        "phase": phase,
        "elapsed_seconds": round(max(0.0, min(float(elapsed), 86_400.0)), 3),
        "detail": detail,
    }


def _uncertainty_snapshot(ask_result, *, observation_index: int) -> dict[str, Any]:
    interpretation = ask_result.interpretation
    assessments = ask_result.assessments
    unresolved_assessments = sum(
        item.result.state is not AssessmentState.Assessed for item in assessments
    )
    unknown_verdicts = sum(
        item.result.verdict is Verdict.U for item in assessments
    )
    open_ontology_targets = sum(
        item.target_id is not None for item in interpretation.ontologies
    )
    structural_open_count = (
        len(interpretation.ambiguities)
        + open_ontology_targets
        + unresolved_assessments
    )
    return {
        "observation_index": observation_index,
        # The provider's interpretation id remains process-local.  Public
        # artifacts use a host-owned observation alias instead.
        "interpretation_id": f"snapshot-{observation_index}",
        "ambiguity_count": len(interpretation.ambiguities),
        "reading_count": len(interpretation.readings),
        "presupposition_count": len(interpretation.presuppositions),
        "open_ontology_target_count": open_ontology_targets,
        "assessment_count": len(assessments),
        "unresolved_assessment_count": unresolved_assessments,
        "unknown_verdict_count": unknown_verdicts,
        "structural_open_count": structural_open_count,
        "landscape": ask_result.landscape.status.value,
        "disposition": ask_result.disposition.value,
        "reason": ask_result.reason,
        # Kept only in memory for comparable-delta classification.  Candidate
        # identifiers and verdicts must not become part of the redaction-safe
        # public artifact.
        "_assessment_states": tuple(
            (
                (
                    item.candidate.id,
                    item.candidate.formalization_id,
                    item.candidate.context_id,
                    item.candidate.reading_id,
                    repr(item.candidate.formalization),
                    item.candidate.assumptions,
                ),
                item.result.verdict,
            )
            for item in assessments
        ),
    }


def _public_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Remove in-memory comparison state before publishing an observation."""

    return {
        key: value
        for key, value in snapshot.items()
        if not key.startswith("_")
    }


def _uncertainty_delta(
    initial: Mapping[str, Any], final: Mapping[str, Any]
) -> dict[str, Any]:
    fields = (
        "ambiguity_count",
        "reading_count",
        "presupposition_count",
        "open_ontology_target_count",
        "assessment_count",
        "unresolved_assessment_count",
        "unknown_verdict_count",
        "structural_open_count",
    )
    delta = {
        f"{field}_delta": int(final[field]) - int(initial[field])
        for field in fields
    }
    structural_reduced = delta["structural_open_count_delta"] < 0
    initial_states = tuple(initial.get("_assessment_states", ()))
    final_states = tuple(final.get("_assessment_states", ()))
    initial_counts = Counter(identity for identity, _ in initial_states)
    final_counts = Counter(identity for identity, _ in final_states)
    comparable = bool(initial_states and final_states) and all(
        count == 1 for count in (*initial_counts.values(), *final_counts.values())
    )
    if comparable:
        final_verdicts = dict(final_states)
        epistemic_reduced = any(
            verdict is Verdict.U
            and identity in final_verdicts
            and final_verdicts[identity] in {Verdict.T, Verdict.F}
            for identity, verdict in initial_states
        )
        epistemic_status = (
            "established"
            if epistemic_reduced
            else (
                "not_established"
                if set(initial_counts) & set(final_counts)
                else "not_comparable"
            )
        )
    else:
        epistemic_reduced = False
        epistemic_status = "not_comparable"
    if structural_reduced and epistemic_reduced:
        observed_reduction = "structural_and_epistemic"
    elif structural_reduced:
        observed_reduction = "structural"
    elif epistemic_reduced:
        observed_reduction = "epistemic"
    else:
        observed_reduction = "none_observed"
    return {
        **delta,
        "structural_reduction_observed": structural_reduced,
        "epistemic_reduction_observed": epistemic_reduced,
        "epistemic_reduction_status": epistemic_status,
        "observed_reduction": observed_reduction,
        "clarification_required_initial": initial["disposition"] == "AskClarification",
        "clarification_required_final": final["disposition"] == "AskClarification",
    }


def _progress_payload(entry, *, question_index: int) -> dict[str, Any]:
    return {
        "question_id": f"question-{question_index}",
        "kind": entry.kind.value,
        "target_count": len(entry.target_ids),
        "new_item_count": len(entry.new_item_ids),
        "new_semantic_signature_count": len(entry.new_semantic_signatures),
        "refinement_operations": list(entry.refinement_operations),
        "refinement_effects": list(entry.refinement_effects),
        "refinement_committed": entry.refinement_committed,
    }


def run_bounded_dialogue(
    *,
    source_text: str,
    interpretation_provider: InterpretationProvider,
    refinement_provider: InterpretationRefinementProvider,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, Any],
    answer_input: Callable[[str], str],
    output_fn: Callable[[str], None] | None = None,
    max_turns: int = 3,
    case_id: str = CASE_ID,
    source_fixture_id: str | None = None,
    model_backed: bool = False,
) -> dict[str, Any]:
    """Run a bounded dialogue while retaining only redaction-safe metadata."""

    if max_turns < 1:
        raise ValueError("max_turns must be positive.")
    events: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    answers_consumed = 0

    def before_answer(session, question: ClarificationQuestion) -> None:
        if session.assessment is None:
            raise ValueError("Clarification session has no assessment before an answer.")
        observations.append(
            _uncertainty_snapshot(
                session.assessment.ask_result,
                observation_index=len(observations),
            )
        )
        if output_fn is not None:
            output_fn(f"Clarification: {question.text}")
            if question.choices:
                output_fn("Choices: " + ", ".join(question.choices))

    def read_answer(prompt: str) -> str:
        nonlocal answers_consumed
        answer = answer_input(prompt)
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("An interactive clarification answer must not be empty.")
        answers_consumed += 1
        return answer

    dialogue = run_interactive_dialogue(
        InterpretationRequest(source_text),
        interpretation_provider=interpretation_provider,
        refinement_provider=refinement_provider,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=ModelClarificationPolicy(
            FixtureClarificationPolicy(), refinement_provider
        ),
        input_fn=read_answer,
        output_fn=output_fn or (lambda _: None),
        before_answer_fn=before_answer,
        max_turns=max_turns,
    )
    assessment = dialogue.session.assessment
    if assessment is None:
        raise ValueError("Prototype ended without a current assessment.")
    final_snapshot = _uncertainty_snapshot(
        assessment.ask_result,
        observation_index=len(observations),
    )
    if not observations:
        observations.append(final_snapshot)
    initial_snapshot = observations[0]
    source_metadata: dict[str, Any]
    if source_fixture_id == CASE_ID and source_text == SOURCE_TEXT:
        source_metadata = {
            "fixture_id": CASE_ID,
            "source_length": len(SOURCE_TEXT),
        }
    else:
        source_metadata = {"source_kind": "unidentified"}
    public_trace = [
        _public_snapshot(snapshot)
        for snapshot in observations + ([final_snapshot] if observations[-1] != final_snapshot else [])
    ]
    return {
        "record_type": "pr47_redaction_safe_multiturn_interactive_prototype",
        "experiment_version": 1,
        "case_id": _PUBLIC_CASE_ALIAS,
        "source": source_metadata,
        "stages": events,
        "answers_consumed": answers_consumed,
        "turns": dialogue.turns,
        "stop_reason": dialogue.stop_reason,
        "uncertainty_trace": public_trace,
        "uncertainty_delta": _uncertainty_delta(initial_snapshot, final_snapshot),
        "progress": [
            _progress_payload(entry, question_index=index)
            for index, entry in enumerate(dialogue.progress.entries)
        ],
        "final": _public_snapshot(final_snapshot),
        "model_run_started": model_backed,
        "provider_payloads_recorded": False,
        "production_admission_changed": False,
        "semantic_adjudication_receipt_created": False,
        "semantic_identity": "not_evaluated",
    }


def run_prototype(
    *,
    endpoint: str,
    model: str,
    context_path: Path,
    max_turns: int = 3,
    timeout: float = 120.0,
    max_output_tokens: int = 768,
    answer_input: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

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
        client, context_ids=tuple(contexts), trace=trace
    )
    result = run_bounded_dialogue(
        source_text=SOURCE_TEXT,
        interpretation_provider=interpretation_provider,
        refinement_provider=interpretation_provider,
        formalization_provider=formalization_provider,
        contexts=contexts,
        answer_input=answer_input,
        output_fn=output_fn,
        max_turns=max_turns,
        case_id=CASE_ID,
        source_fixture_id=CASE_ID,
        model_backed=True,
    )
    result["provider"] = {
        "endpoint": _safe_endpoint(endpoint),
        "model": _safe_model(model),
        "temperature": 0.0,
        "max_output_tokens": max_output_tokens,
        "thinking_enabled": False,
    }
    result["stages"] = events
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-turns", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-output-tokens", type=int, default=768)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = run_prototype(
        endpoint=args.endpoint,
        model=args.model,
        context_path=args.context,
        max_turns=args.max_turns,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
