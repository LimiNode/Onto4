"""The small deterministic ``onto4`` command-line interface."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from onto4.core import AssessmentResult
from onto4.pipeline.compare import compare_files
from onto4.pipeline.eval import evaluate_files


def _result_dict(result: AssessmentResult) -> dict[str, Any]:
    return {
        "semantic_status": result.semantic_status.value,
        "verdict": result.verdict.value if result.verdict else None,
        "evidence": result.evidence.value,
        "unknown_reasons": [reason.value for reason in result.unknown_reasons],
        "diagnostics": [asdict(item) for item in result.diagnostics],
    }


def _print_result(result: AssessmentResult, context_name: str | None = None) -> None:
    if context_name:
        print(f"Context: {context_name}")
    print(f"Semantic status: {result.semantic_status.value}")
    print(f"Onto4: {result.verdict.value if result.verdict else '—'}")
    print(f"Evidence: {result.evidence.value}")
    if result.unknown_reasons:
        print("Reasons: " + ", ".join(reason.value for reason in result.unknown_reasons))
    for diagnostic in result.diagnostics:
        print(f"Diagnostic [{diagnostic.code}]: {diagnostic.message}")


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

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
