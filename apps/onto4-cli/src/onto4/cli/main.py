"""The small deterministic ``onto4`` command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from onto4.core import AssessmentResult
from onto4.pipeline.ask import ask
from onto4.pipeline.compare import compare_files
from onto4.pipeline.eval import evaluate_files
from onto4.pipeline.loaders import load_context
from onto4.providers import (
    EndpointAuthKind,
    OpenAICompatibleClient,
    OpenAICompatibleFormalizationProvider,
    OpenAICompatibleInterpretationProvider,
    ProviderProfile,
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


def _ask_dict(result: Any) -> dict[str, Any]:
    return {
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


def _print_ask_result(result: Any) -> None:
    print(f"Interpretation: {result.interpretation.id}")
    print(f"Conceptual depth: {result.interpretation.conceptual_depth.value}")
    print(f"Landscape: {result.landscape.status.value}")
    print(f"Disposition: {result.disposition.value}")
    if result.reason:
        print(f"Reason: {result.reason}")
    for item in result.assessments:
        verdict = item.result.verdict.value if item.result.verdict else "—"
        print(f"Candidate {item.candidate.id}: Onto4 {verdict}")
    if result.clarification_question is not None:
        print(f"Clarification: {result.clarification_question.text}")
        if result.clarification_question.choices:
            print("Choices: " + ", ".join(result.clarification_question.choices))


def _run_ask(args: argparse.Namespace) -> int:
    try:
        auth = EndpointAuthKind(args.auth)
        profile = ProviderProfile(
            base_url=args.endpoint,
            model=args.model,
            auth=auth,
            timeout_seconds=args.timeout,
        )
        token = os.environ.get(args.token_env) if auth is EndpointAuthKind.Bearer else None
        client = OpenAICompatibleClient(profile, bearer_token=token)
        depth = None if args.depth == "auto" else ConceptualDepth(args.depth)
        contexts = {}
        for context_path in args.context:
            path = Path(context_path)
            context_id = path.stem
            if context_id in contexts:
                raise ValueError(f"Duplicate context id from --context: {context_id!r}.")
            contexts[context_id] = load_context(path)

        result = ask(
            InterpretationRequest(args.text, conceptual_depth=depth),
            interpretation_provider=OpenAICompatibleInterpretationProvider(client),
            formalization_provider=OpenAICompatibleFormalizationProvider(
                client,
                context_ids=tuple(contexts),
            ),
            contexts=contexts,
            clarification_policy=FixtureClarificationPolicy(),
        )
    except (
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
        print(json.dumps(_ask_dict(result), ensure_ascii=False, indent=2))
    else:
        _print_ask_result(result)
    return 0


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

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
