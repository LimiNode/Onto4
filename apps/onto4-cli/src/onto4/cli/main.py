"""The small deterministic ``onto4`` command-line interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from onto4.core import AssessmentResult
from onto4.pipeline import (
    EvaluationConfig,
    ModelClarificationPolicy,
    ModelCaseExecutor,
    SequentialEvaluationRunner,
    ask_per_reading,
    corpus_digest,
    load_clarification_corpus,
    offline_fixture_executor,
    run_interactive_dialogue,
    write_markdown_report,
)
from onto4.pipeline.compare import compare_files
from onto4.pipeline.eval import evaluate_files
from onto4.pipeline.loaders import load_context
from onto4.providers import (
    EndpointAuthKind,
    OpenAICompatibleClient,
    OpenAICompatibleFormalizationProvider,
    OpenAICompatibleInterpretationProvider,
    ProviderProfile,
    ProviderStageEvent,
    ProviderSchemaError,
    ProviderTransportError,
)
from onto4.reasoning import ConceptualDepth, FixtureClarificationPolicy
from onto4.providers import InterpretationRequest


def _result_dict(result: AssessmentResult) -> dict[str, Any]:
    return {
        "state": result.state.value,
        "semantic_status": result.semantic_status.value if result.semantic_status else None,
        "verdict": result.verdict.value if result.verdict else None,
        "evidence": result.evidence.value if result.evidence else None,
        "unknown_reasons": [reason.value for reason in result.unknown_reasons],
        "diagnostics": [asdict(item) for item in result.diagnostics],
    }


def _print_result(result: AssessmentResult, context_name: str | None = None) -> None:
    if context_name:
        print(f"Context: {context_name}")
    print(f"State: {result.state.value}")
    print(f"Semantic status: {result.semantic_status.value if result.semantic_status else '—'}")
    print(f"Onto4: {result.verdict.value if result.verdict else '—'}")
    print(f"Evidence: {result.evidence.value if result.evidence else '—'}")
    if result.unknown_reasons:
        print("Reasons: " + ", ".join(reason.value for reason in result.unknown_reasons))
    for diagnostic in result.diagnostics:
        print(f"Diagnostic [{diagnostic.code}]: {diagnostic.message}")


def _ask_dict(result: Any, *, stop_reason: str | None = None) -> dict[str, Any]:
    payload = {
        "interpretation": {
            "id": result.interpretation.id,
            "source_text": result.interpretation.source_text,
            "conceptual_depth": result.interpretation.conceptual_depth.value,
            "readings": [reading.id for reading in result.interpretation.readings],
        },
        "candidates": [
            {
                "id": candidate.id,
                "formalization_id": candidate.formalization_id,
                "context_id": candidate.context_id,
                "reading_id": candidate.reading_id,
            }
            for candidate in result.candidates
        ],
        "landscape": result.landscape.status.value,
        "disposition": result.disposition.value,
        "reason": result.reason,
        "clarification": (
            {
                "id": result.clarification_question.id,
                "kind": result.clarification_question.kind.value,
                "text": result.clarification_question.text,
                "choices": list(result.clarification_question.choices),
            }
            if result.clarification_question is not None
            else None
        ),
        "assessments": [
            {
                "candidate_id": item.candidate.id,
                "state": item.result.state.value,
                "verdict": item.result.verdict.value if item.result.verdict else None,
                "evidence": item.result.evidence.value if item.result.evidence else None,
            }
            for item in result.assessments
        ],
    }
    if stop_reason is not None:
        payload["stop_reason"] = stop_reason
    return payload


def _print_ask_result(result: Any, *, stop_reason: str | None = None) -> None:
    print(f"Interpretation: {result.interpretation.id}")
    print(f"Conceptual depth: {result.interpretation.conceptual_depth.value}")
    print(f"Landscape: {result.landscape.status.value}")
    print(f"Disposition: {result.disposition.value}")
    if result.reason:
        print(f"Reason: {result.reason}")
    for item in result.assessments:
        verdict = item.result.verdict.value if item.result.verdict else "—"
        print(f"Candidate {item.candidate.id}: Onto4 {verdict}")
    if (
        result.clarification_question is not None
        and stop_reason != "max_turns_reached"
    ):
        print(f"Clarification: {result.clarification_question.text}")
        if result.clarification_question.choices:
            print("Choices: " + ", ".join(result.clarification_question.choices))
    if stop_reason is not None:
        print(f"Stop reason: {stop_reason}")


def _print_provider_trace(event: ProviderStageEvent) -> None:
    detail = f" [{event.detail}]" if event.detail else ""
    print(
        f"[onto4] {event.stage}: {event.phase} ({event.elapsed_seconds:.3f}s){detail}",
        file=sys.stderr,
    )


def _run_ask(args: argparse.Namespace) -> int:
    try:
        if args.interactive and args.format == "json":
            raise ValueError(
                "Interactive ask does not support --format json; use text output."
            )
        auth = EndpointAuthKind(args.auth)
        profile = ProviderProfile(
            base_url=args.endpoint,
            model=args.model,
            auth=auth,
            timeout_seconds=args.timeout,
            max_output_tokens=args.max_output_tokens,
            disable_thinking=not args.enable_thinking,
            temperature=args.temperature,
        )
        token = os.environ.get(args.token_env) if auth is EndpointAuthKind.Bearer else None
        client = OpenAICompatibleClient(profile, bearer_token=token)
        depth = None if args.depth == "auto" else ConceptualDepth(args.depth)
        trace = _print_provider_trace if args.debug else None
        contexts = {}
        for context_path in args.context:
            path = Path(context_path)
            context_id = path.stem
            if context_id in contexts:
                raise ValueError(f"Duplicate context id from --context: {context_id!r}.")
            contexts[context_id] = load_context(path)

        interpretation_provider = OpenAICompatibleInterpretationProvider(
            client,
            trace=trace,
        )
        formalization_provider = OpenAICompatibleFormalizationProvider(
            client,
            context_ids=tuple(contexts),
            trace=trace,
        )
        request = InterpretationRequest(args.text, conceptual_depth=depth)
        if args.interactive:
            dialogue_policy = ModelClarificationPolicy(
                FixtureClarificationPolicy(),
                interpretation_provider,
            )
            dialogue = run_interactive_dialogue(
                request,
                interpretation_provider=interpretation_provider,
                refinement_provider=interpretation_provider,
                formalization_provider=formalization_provider,
                contexts=contexts,
                clarification_policy=dialogue_policy,
                max_turns=args.max_turns,
            )
            if dialogue.session.assessment is None:
                raise ValueError("Interactive dialogue ended without an assessment.")
            result = dialogue.session.assessment.ask_result
            stop_reason = dialogue.stop_reason
        else:
            result = ask_per_reading(
                request,
                interpretation_provider=interpretation_provider,
                formalization_provider=formalization_provider,
                contexts=contexts,
                clarification_policy=FixtureClarificationPolicy(),
            )
            stop_reason = None
    except (
        EOFError,
        KeyError,
        OSError,
        ProviderTransportError,
        ProviderSchemaError,
        ValueError,
        yaml.YAMLError,
    ) as exc:
        print(f"Ask error: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(_ask_dict(result, stop_reason=stop_reason), ensure_ascii=False, indent=2))
    else:
        _print_ask_result(result, stop_reason=stop_reason)
    return 0


def _run_eval_corpus(args: argparse.Namespace) -> int:
    try:
        corpus = load_clarification_corpus(args.corpus)
        digest = corpus_digest(args.corpus)
        contexts = {}
        requested_depth = (
            None if args.depth == "auto" else ConceptualDepth(args.depth)
        )
        if args.mode == "model-backed":
            if not args.endpoint or not args.model:
                raise ValueError("Model-backed evaluation requires --endpoint and --model.")
            if not args.context:
                raise ValueError("Model-backed evaluation requires at least one --context.")
            auth = EndpointAuthKind(args.auth)
            token = os.environ.get(args.token_env) if auth is EndpointAuthKind.Bearer else None
            profile = ProviderProfile(
                base_url=args.endpoint,
                model=args.model,
                auth=auth,
                timeout_seconds=args.timeout,
                max_output_tokens=args.max_output_tokens,
                disable_thinking=not args.enable_thinking,
                temperature=args.temperature,
            )
            client = OpenAICompatibleClient(profile, bearer_token=token)
            for context_path in args.context:
                context_id = context_path.stem
                if context_id in contexts:
                    raise ValueError(f"Duplicate context id from --context: {context_id!r}.")
                contexts[context_id] = load_context(context_path)
            trace = _print_provider_trace if args.debug else None
            interpretation_adapter = OpenAICompatibleInterpretationProvider(
                client, prompt_variant=args.prompt_variant
            )
            formalization_adapter = OpenAICompatibleFormalizationProvider(
                client, context_ids=tuple(contexts)
            )
            executor = ModelCaseExecutor(
                interpretation_adapter,
                formalization_adapter,
                contexts,
                max_turns=args.max_turns,
                requested_conceptual_depth=requested_depth,
                trace_sink=trace,
            )
            interpretation_adapter.trace = executor.provider_trace
            formalization_adapter.trace = executor.provider_trace
            provider = "openai-compatible"
            model = args.model
        else:
            executor = offline_fixture_executor
            provider = "fixture"
            model = "offline-fixture"
        config = EvaluationConfig(
            request_timeout_seconds=args.timeout,
            case_deadline_seconds=args.case_deadline,
            inter_case_delay_seconds=args.inter_case_delay,
            max_retries=args.max_retries,
            provider=provider,
            model=model,
            mode=args.mode,
            prompt_version=args.prompt_version,
            prompt_hash=args.prompt_hash,
            commit_sha=os.environ.get("ONTO4_COMMIT_SHA"),
            model_artifact_digest=args.model_artifact_digest,
            temperature=args.temperature if args.mode == "model-backed" else None,
            thinking_enabled=args.enable_thinking if args.mode == "model-backed" else None,
            max_output_tokens=args.max_output_tokens if args.mode == "model-backed" else None,
            variant=args.variant,
            prompt_variant=args.prompt_variant,
            requested_conceptual_depth=(
                requested_depth.value if requested_depth is not None else "auto"
            ),
            run_id=args.run_id,
            context_profile_digests={
                path.stem: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in args.context or ()
            },
        )
        run = SequentialEvaluationRunner(
            executor,
            config=config,
            receipt_path=args.receipt,
        ).run(corpus, digest=digest)
        write_markdown_report(run, args.report)
        print(json.dumps({
            "corpus": run.corpus_name,
            "cases": run.summary.total_cases,
            "completed": run.summary.completed_cases,
            "receipt": str(args.receipt),
            "report": str(args.report),
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Evaluation error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="onto4")
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser("eval", help="Evaluate a formalization in one context.")
    eval_parser.add_argument("formalization", type=Path)
    eval_parser.add_argument("--context", required=True, type=Path)
    eval_parser.add_argument("--format", choices=("text", "json"), default="text")

    compare_parser = subparsers.add_parser("compare", help="Evaluate one formalization under several contexts.")
    compare_parser.add_argument("formalization", type=Path)
    compare_parser.add_argument("--context", action="append", required=True, type=Path)
    compare_parser.add_argument("--format", choices=("text", "json"), default="text")

    ask_parser = subparsers.add_parser(
        "ask", help="Run one model-backed interpretation and deterministic assessment pass."
    )
    ask_parser.add_argument("text", help="Natural-language statement to assess.")
    ask_parser.add_argument("--endpoint", required=True, help="OpenAI-compatible base URL.")
    ask_parser.add_argument("--model", required=True, help="Model name accepted by the endpoint.")
    ask_parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Provider request timeout in seconds (default: 30).",
    )
    ask_parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=1024,
        help="Bound model output per provider request (default: 1024).",
    )
    ask_parser.add_argument(
        "--enable-thinking",
        action="store_true",
        help="Allow provider-side hidden reasoning (disabled by default for JSON stages).",
    )
    ask_parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0 for reproducible structured output).",
    )
    ask_parser.add_argument("--auth", choices=("none", "bearer"), default="none")
    ask_parser.add_argument(
        "--token-env",
        default="ONTO4_API_TOKEN",
        help="Environment variable containing a Bearer token (never printed).",
    )
    ask_parser.add_argument(
        "--depth",
        choices=("auto", *(depth.value for depth in ConceptualDepth)),
        default="auto",
    )
    ask_parser.add_argument("--context", action="append", required=True, type=Path)
    ask_parser.add_argument("--format", choices=("text", "json"), default="text")
    ask_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print safe provider-stage timing diagnostics to stderr.",
    )
    ask_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run bounded clarification, free-form answers and explicit reassessment.",
    )
    ask_parser.add_argument(
        "--max-turns",
        type=int,
        default=4,
        help="Maximum interactive clarification turns (default: 4).",
    )

    corpus_parser = subparsers.add_parser(
        "eval-corpus",
        help="Run the clarification corpus sequentially and write safe receipts.",
    )
    corpus_parser.add_argument("--corpus", required=True, type=Path)
    corpus_parser.add_argument("--receipt", required=True, type=Path)
    corpus_parser.add_argument("--report", required=True, type=Path)
    corpus_parser.add_argument("--timeout", type=float, default=30.0)
    corpus_parser.add_argument("--case-deadline", type=float, default=120.0)
    corpus_parser.add_argument("--inter-case-delay", type=float, default=0.0)
    corpus_parser.add_argument("--max-retries", type=int, default=0)
    corpus_parser.add_argument("--prompt-version", default="unspecified")
    corpus_parser.add_argument(
        "--depth",
        choices=("auto", *(depth.value for depth in ConceptualDepth)),
        default="auto",
        help="Requested interpretation depth for model-backed runs (default: auto).",
    )
    corpus_parser.add_argument(
        "--prompt-variant",
        choices=("baseline", "explicit_depth", "compact_json"),
        default="baseline",
    )
    corpus_parser.add_argument("--prompt-hash")
    corpus_parser.add_argument("--model-artifact-digest")
    corpus_parser.add_argument(
        "--mode", choices=("offline", "model-backed"), default="offline",
        help="Use deterministic protocol coverage or real provider execution.",
    )
    corpus_parser.add_argument("--endpoint", help="OpenAI-compatible base URL (model-backed).")
    corpus_parser.add_argument("--model", help="Provider model identifier (model-backed).")
    corpus_parser.add_argument("--auth", choices=("none", "bearer"), default="none")
    corpus_parser.add_argument("--token-env", default="ONTO4_API_TOKEN")
    corpus_parser.add_argument("--context", action="append", type=Path)
    corpus_parser.add_argument("--max-output-tokens", type=int, default=1024)
    corpus_parser.add_argument("--temperature", type=float, default=0.0)
    corpus_parser.add_argument("--enable-thinking", action="store_true")
    corpus_parser.add_argument("--max-turns", type=int, default=4)
    corpus_parser.add_argument("--variant", default="default")
    corpus_parser.add_argument("--run-id")
    corpus_parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "eval":
        result = evaluate_files(args.formalization, args.context)
        if args.format == "json":
            print(json.dumps(_result_dict(result), ensure_ascii=False, indent=2))
        else:
            _print_result(result, args.context.stem)
        return 0

    if args.command == "compare":
        results = compare_files(args.formalization, args.context)
        if args.format == "json":
            print(
                json.dumps(
                    [{"context": name, "result": _result_dict(result)} for name, result in results],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            for index, (name, result) in enumerate(results):
                if index:
                    print()
                _print_result(result, Path(name).stem)
        return 0

    if args.command == "ask":
        return _run_ask(args)

    if args.command == "eval-corpus":
        return _run_eval_corpus(args)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
