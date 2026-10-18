"""Controlled paired A/B benchmark over the model-backed corpus runner."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Mapping

from .clarification_corpus import ClarificationCorpus, ClarificationCorpusCase
from .evaluation import (
    CaseExecutor,
    CaseReceipt,
    EvaluationConfig,
    EvaluationOutcome,
    EvaluationRun,
    SequentialEvaluationRunner,
)


_COMPLETION_TOKENS = re.compile(r"completion_tokens=(?P<tokens>[0-9]{1,9})")


@dataclass(frozen=True)
class BenchmarkCondition:
    """One cell in the frozen 2x2 interpretation/refinement design."""

    name: str
    interpretation_context_mode: str
    refinement_mode: str

    def __post_init__(self) -> None:
        if self.name not in {"A1", "A2", "B1", "B2"}:
            raise ValueError("benchmark condition name must be A1, A2, B1 or B2.")
        if self.interpretation_context_mode not in {"context_late", "context_aware"}:
            raise ValueError("benchmark condition has an invalid context mode.")
        if self.refinement_mode not in {"full_snapshot", "typed_delta"}:
            raise ValueError("benchmark condition has an invalid refinement mode.")


DEFAULT_BENCHMARK_CONDITIONS = (
    BenchmarkCondition("A1", "context_late", "full_snapshot"),
    BenchmarkCondition("A2", "context_aware", "full_snapshot"),
    BenchmarkCondition("B1", "context_late", "typed_delta"),
    BenchmarkCondition("B2", "context_aware", "typed_delta"),
)


@dataclass(frozen=True)
class BenchmarkCell:
    condition: str
    case_id: str
    outcome: str
    oracle_match: bool | None
    semantic_verdict: str | None
    clarification_turns: int
    provider_calls: int
    completion_tokens: int
    elapsed_seconds: float


@dataclass(frozen=True)
class PairedBenchmarkSummary:
    total_cases: int
    oracle_comparable_observations: int
    oracle_passed_observations: int
    semantic_errors: int
    operational_failures: int
    clarification_turns: Mapping[str, int]
    provider_calls: Mapping[str, int]
    completion_tokens: Mapping[str, int]
    estimated_output_cost_usd: Mapping[str, float]
    elapsed_seconds: Mapping[str, float]
    pair_wins: Mapping[str, Mapping[str, int]]


@dataclass(frozen=True)
class PairedBenchmarkRun:
    corpus_name: str
    corpus_version: int
    corpus_digest: str
    conditions: tuple[BenchmarkCondition, ...]
    runs: Mapping[str, EvaluationRun]
    cells: tuple[BenchmarkCell, ...]
    summary: PairedBenchmarkSummary


def _completion_tokens(receipt: CaseReceipt) -> int:
    return sum(
        int(match.group("tokens"))
        for detail in receipt.provider_stage_details.values()
        for match in [_COMPLETION_TOKENS.search(str(detail))]
        if match is not None
    )


def _oracle_match(
    case: ClarificationCorpusCase,
    receipt: CaseReceipt,
) -> bool | None:
    expected = case.expected_after_answer
    expected_verdict = expected.get("verdict")
    expected_disposition = expected.get("disposition")
    checks: list[bool] = []
    if isinstance(expected_verdict, str):
        checks.append(receipt.semantic_verdict == expected_verdict)
    if isinstance(expected_disposition, str):
        disposition_outcomes = {
            "complete": {EvaluationOutcome.ASSESSMENT_COMPLETED},
            "clarification_required": {
                EvaluationOutcome.CLARIFICATION_REQUESTED,
                EvaluationOutcome.DIALOGUE_INCOMPLETE,
            },
            "dialogue_reassessment_required": {
                EvaluationOutcome.ASSESSMENT_COMPLETED,
                EvaluationOutcome.CLARIFICATION_REQUESTED,
                EvaluationOutcome.DIALOGUE_INCOMPLETE,
            },
        }
        allowed = disposition_outcomes.get(expected_disposition)
        if allowed is not None:
            checks.append(receipt.outcome in allowed)
    if not checks:
        return None
    return all(checks)


def _cell(
    condition: BenchmarkCondition,
    case: ClarificationCorpusCase,
    receipt: CaseReceipt,
) -> BenchmarkCell:
    return BenchmarkCell(
        condition=condition.name,
        case_id=case.case_id,
        outcome=receipt.outcome.value,
        oracle_match=_oracle_match(case, receipt),
        semantic_verdict=receipt.semantic_verdict,
        clarification_turns=int(receipt.diagnostics.get("clarification_turns", 0)),
        provider_calls=receipt.provider_calls,
        completion_tokens=_completion_tokens(receipt),
        elapsed_seconds=receipt.elapsed_seconds,
    )


def _summary(
    conditions: tuple[BenchmarkCondition, ...],
    cells: tuple[BenchmarkCell, ...],
    *,
    output_cost_per_million: float,
) -> PairedBenchmarkSummary:
    clarification_turns = {condition.name: 0 for condition in conditions}
    provider_calls = {condition.name: 0 for condition in conditions}
    completion_tokens = {condition.name: 0 for condition in conditions}
    estimated_output_cost_usd = {condition.name: 0.0 for condition in conditions}
    elapsed_seconds = {condition.name: 0.0 for condition in conditions}
    oracle_observations = 0
    oracle_passed = 0
    semantic_errors = 0
    operational_failures = 0
    for cell in cells:
        clarification_turns[cell.condition] += cell.clarification_turns
        provider_calls[cell.condition] += cell.provider_calls
        completion_tokens[cell.condition] += cell.completion_tokens
        estimated_output_cost_usd[cell.condition] += (
            cell.completion_tokens * output_cost_per_million / 1_000_000
        )
        elapsed_seconds[cell.condition] += cell.elapsed_seconds
        if cell.oracle_match is not None:
            oracle_observations += 1
            oracle_passed += int(cell.oracle_match)
            semantic_errors += int(not cell.oracle_match)
        if cell.outcome in {
            EvaluationOutcome.TRANSPORT_ERROR.value,
            EvaluationOutcome.REQUEST_TIMEOUT.value,
            EvaluationOutcome.CASE_DEADLINE_EXCEEDED.value,
            EvaluationOutcome.SCHEMA_INVALID.value,
            EvaluationOutcome.PROVENANCE_INVALID.value,
        }:
            operational_failures += 1

    pair_wins = {
        "A1_vs_B1": {"A1": 0, "B1": 0, "tie": 0},
        "A1_vs_A2": {"A1": 0, "A2": 0, "tie": 0},
        "B1_vs_B2": {"B1": 0, "B2": 0, "tie": 0},
    }
    by_case = {}
    for cell in cells:
        by_case.setdefault(cell.case_id, {})[cell.condition] = cell
    for case_cells in by_case.values():
        for pair_name, left_name, right_name in (
            ("A1_vs_B1", "A1", "B1"),
            ("A1_vs_A2", "A1", "A2"),
            ("B1_vs_B2", "B1", "B2"),
        ):
            left, right = case_cells.get(left_name), case_cells.get(right_name)
            if (
                left is None
                or right is None
                or left.oracle_match is None
                or right.oracle_match is None
            ):
                continue
            if left.oracle_match == right.oracle_match:
                pair_wins[pair_name]["tie"] += 1
            elif left.oracle_match:
                pair_wins[pair_name][left_name] += 1
            else:
                pair_wins[pair_name][right_name] += 1
    return PairedBenchmarkSummary(
        total_cases=len(by_case),
        oracle_comparable_observations=oracle_observations,
        oracle_passed_observations=oracle_passed,
        semantic_errors=semantic_errors,
        operational_failures=operational_failures,
        clarification_turns=clarification_turns,
        provider_calls=provider_calls,
        completion_tokens=completion_tokens,
        estimated_output_cost_usd=estimated_output_cost_usd,
        elapsed_seconds=elapsed_seconds,
        pair_wins=pair_wins,
    )


def run_paired_benchmark(
    corpus: ClarificationCorpus,
    *,
    executor_factory: Callable[[BenchmarkCondition], CaseExecutor],
    config: EvaluationConfig,
    receipt_dir: str | Path | None = None,
    output_cost_per_million: float = 0.0,
    conditions: tuple[BenchmarkCondition, ...] = DEFAULT_BENCHMARK_CONDITIONS,
) -> PairedBenchmarkRun:
    """Run all design cells over the same corpus and budget contract."""

    if output_cost_per_million < 0:
        raise ValueError("output_cost_per_million must not be negative.")

    digest = corpus_digest_for_loaded(corpus)
    runs: dict[str, EvaluationRun] = {}
    cells: list[BenchmarkCell] = []
    artifact_dir = Path(receipt_dir) if receipt_dir is not None else None
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    for condition in conditions:
        condition_config = replace(
            config,
            variant=condition.name,
            interpretation_context_mode=condition.interpretation_context_mode,
            refinement_mode=condition.refinement_mode,
        )
        receipt_path = (
            artifact_dir / f"{condition.name}.receipts.jsonl"
            if artifact_dir is not None
            else None
        )
        result = SequentialEvaluationRunner(
            executor_factory(condition),
            config=condition_config,
            receipt_path=receipt_path,
        ).run(corpus, digest=digest)
        runs[condition.name] = result
        by_id = {receipt.case_id: receipt for receipt in result.receipts}
        cells.extend(
            _cell(condition, case, by_id[case.case_id])
            for case in corpus.cases
        )
    cell_tuple = tuple(cells)
    return PairedBenchmarkRun(
        corpus_name=corpus.name,
        corpus_version=corpus.version,
        corpus_digest=digest,
        conditions=conditions,
        runs=runs,
        cells=cell_tuple,
        summary=_summary(
            conditions,
            cell_tuple,
            output_cost_per_million=output_cost_per_million,
        ),
    )


def corpus_digest_for_loaded(corpus: ClarificationCorpus) -> str:
    """Compute a stable digest from the loaded public corpus structure."""

    payload = {
        "version": corpus.version,
        "name": corpus.name,
        "model_input": corpus.model_input,
        "context_profiles": dict(sorted(corpus.context_profiles.items())),
        "cases": [asdict(case) for case in corpus.cases],
    }
    import hashlib

    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=list).encode("utf-8")
    ).hexdigest()


def write_benchmark_report(run: PairedBenchmarkRun, path: str | Path) -> None:
    target = Path(path)
    payload = {
        "corpus_name": run.corpus_name,
        "corpus_version": run.corpus_version,
        "corpus_digest": run.corpus_digest,
        "conditions": [asdict(condition) for condition in run.conditions],
        "summary": asdict(run.summary),
        "cells": [asdict(cell) for cell in run.cells],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "BenchmarkCell",
    "BenchmarkCondition",
    "DEFAULT_BENCHMARK_CONDITIONS",
    "PairedBenchmarkRun",
    "PairedBenchmarkSummary",
    "corpus_digest_for_loaded",
    "run_paired_benchmark",
    "write_benchmark_report",
]
