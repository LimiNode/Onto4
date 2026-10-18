"""Bounded multi-turn dialogue research helpers.

This layer records dialogue-stage outcomes separately from semantic scoring and
offers a model-backed isolated refinement adapter.  It does not assign an
Onto4 verdict and it never relaxes the existing replay or provenance checks.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from onto4.providers import (
    InterpretationRefinementProvider,
    RefinementDeltaProvider,
)
from onto4.reasoning import (
    ClarificationQuestion,
    ClarificationTurn,
    FixtureClarificationPolicy,
    InterpretationSpace,
)

from .ab_benchmark import (
    BenchmarkCondition,
    PairedBenchmarkRun,
    run_isolated_refinement_pair,
    run_paired_benchmark,
)
from .clarification_corpus import ClarificationCorpus
from .evaluation import CaseExecutor, EvaluationConfig
from .interactive import ModelClarificationPolicy, TypedDeltaClarificationPolicy


@dataclass(frozen=True)
class DialogueResearchCell:
    """Stage-level observation for one dialogue case and one condition."""

    condition: str
    case_id: str
    outcome: str
    execution_status: str
    question_issued: bool | None
    answer_consumed: bool | None
    refinement_accepted: bool | None
    reassessment_performed: bool | None
    dialogue_status: str
    semantic_status: str
    semantic_verdict: str | None
    provider_calls: int
    completion_tokens: int
    elapsed_seconds: float
    detail_code: str | None


@dataclass(frozen=True)
class BoundedDialogueResearchRun:
    """A dialogue-only projection of the paired benchmark run."""

    paired_run: PairedBenchmarkRun
    cells: tuple[DialogueResearchCell, ...]
    stage_counts: Mapping[str, Mapping[str, Mapping[str, int]]]
    metadata: Mapping[str, object]


def _stage_flag(value: object, *, positive: bool = True) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value > 0 if positive else bool(value)
    return None


def _dialogue_status(
    question_issued: bool | None,
    answer_consumed: bool | None,
    refinement_accepted: bool | None,
    reassessment_performed: bool | None,
) -> str:
    stages = (
        question_issued,
        answer_consumed,
        refinement_accepted,
        reassessment_performed,
    )
    if any(stage is False for stage in stages):
        return "incomplete"
    if any(stage is None for stage in stages):
        return "unverified"
    return "complete"


def _cell_from_benchmark(cell) -> DialogueResearchCell:
    diagnostics = cell.workflow_diagnostics
    question_issued = _stage_flag(diagnostics.get("questions_issued"))
    answer_consumed = _stage_flag(diagnostics.get("answers_consumed"))
    refinement_accepted = _stage_flag(diagnostics.get("refinement_accepted"))
    reassessment_performed = _stage_flag(diagnostics.get("reassessment_performed"))
    return DialogueResearchCell(
        condition=cell.condition,
        case_id=cell.case_id,
        outcome=cell.outcome,
        execution_status=cell.execution_status,
        question_issued=question_issued,
        answer_consumed=answer_consumed,
        refinement_accepted=refinement_accepted,
        reassessment_performed=reassessment_performed,
        dialogue_status=_dialogue_status(
            question_issued,
            answer_consumed,
            refinement_accepted,
            reassessment_performed,
        ),
        semantic_status=cell.semantic_status,
        semantic_verdict=cell.semantic_verdict,
        provider_calls=cell.provider_calls,
        completion_tokens=cell.completion_tokens,
        elapsed_seconds=cell.elapsed_seconds,
        detail_code=(
            str(diagnostics.get("detail_code"))
            if diagnostics.get("detail_code") is not None
            else None
        ),
    )


def run_bounded_dialogue_research(
    corpus: ClarificationCorpus,
    *,
    executor_factory: Callable[[BenchmarkCondition], CaseExecutor],
    config: EvaluationConfig,
    receipt_dir: str | Path | None = None,
    output_cost_per_million: float | None = None,
    conditions: tuple[BenchmarkCondition, ...] | None = None,
    metadata: Mapping[str, object] | None = None,
) -> BoundedDialogueResearchRun:
    """Run only dialogue cases while preserving the paired benchmark contract."""

    dialogue_cases = tuple(case for case in corpus.cases if case.mode == "dialogue")
    if not dialogue_cases:
        raise ValueError("Bounded dialogue research requires at least one dialogue case.")
    dialogue_corpus = ClarificationCorpus(
        version=corpus.version,
        name=corpus.name,
        cases=dialogue_cases,
        model_input=corpus.model_input,
        context_profiles=corpus.context_profiles,
    )
    kwargs = {} if conditions is None else {"conditions": conditions}
    paired = run_paired_benchmark(
        dialogue_corpus,
        executor_factory=executor_factory,
        config=config,
        receipt_dir=receipt_dir,
        output_cost_per_million=output_cost_per_million,
        metadata={
            **dict(metadata or {}),
            "benchmark_type": "bounded_multiturn_dialogue",
            "dialogue_case_ids": [case.case_id for case in dialogue_cases],
        },
        **kwargs,
    )
    cells = tuple(_cell_from_benchmark(cell) for cell in paired.cells)
    stage_counts: dict[str, dict[str, dict[str, int]]] = {}
    for cell in cells:
        condition_counts = stage_counts.setdefault(cell.condition, {})
        for name, value in (
            ("question_issued", cell.question_issued),
            ("answer_consumed", cell.answer_consumed),
            ("refinement_accepted", cell.refinement_accepted),
            ("reassessment_performed", cell.reassessment_performed),
        ):
            counts = condition_counts.setdefault(
                name, {"true": 0, "false": 0, "unknown": 0}
            )
            bucket = "unknown" if value is None else ("true" if value else "false")
            counts[bucket] += 1
    return BoundedDialogueResearchRun(
        paired_run=paired,
        cells=cells,
        stage_counts=stage_counts,
        metadata={
            **dict(paired.metadata),
            "stage_contract": [
                "question_issued",
                "answer_consumed",
                "refinement_accepted",
                "reassessment_performed",
            ],
        },
    )


def write_dialogue_research_report(
    run: BoundedDialogueResearchRun,
    path: str | Path,
) -> None:
    """Write stage-level research output without prompts or model payloads."""

    target = Path(path)
    payload = {
        "record_type": "bounded_dialogue_research",
        "metadata": dict(run.metadata),
        "paired_summary": asdict(run.paired_run.summary),
        "stage_counts": run.stage_counts,
        "cells": [asdict(cell) for cell in run.cells],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_model_backed_isolated_refinement_pair(
    initial: InterpretationSpace,
    question: ClarificationQuestion,
    answer: str,
    *,
    full_snapshot_provider: InterpretationRefinementProvider,
    typed_delta_provider: RefinementDeltaProvider,
    case_id: str = "model-isolated-refinement",
):
    """Compare model-backed Full Snapshot and Typed Delta from one snapshot."""

    full_policy = ModelClarificationPolicy(
        FixtureClarificationPolicy(), full_snapshot_provider
    )
    typed_policy = TypedDeltaClarificationPolicy(
        FixtureClarificationPolicy(), typed_delta_provider
    )

    def full_snapshot(
        interpretation: InterpretationSpace,
        issued_question: ClarificationQuestion,
        issued_answer: str,
    ) -> tuple[InterpretationSpace, ClarificationTurn]:
        return full_policy.successor(
            interpretation=interpretation,
            question=issued_question,
            answer=issued_answer,
        )

    def typed_delta(
        interpretation: InterpretationSpace,
        issued_question: ClarificationQuestion,
        issued_answer: str,
    ) -> tuple[InterpretationSpace, ClarificationTurn]:
        return typed_policy.successor(
            interpretation=interpretation,
            question=issued_question,
            answer=issued_answer,
        )

    return run_isolated_refinement_pair(
        initial,
        question,
        answer,
        full_snapshot=full_snapshot,
        typed_delta=typed_delta,
        case_id=case_id,
    )


__all__ = [
    "BoundedDialogueResearchRun",
    "DialogueResearchCell",
    "run_bounded_dialogue_research",
    "run_model_backed_isolated_refinement_pair",
    "write_dialogue_research_report",
]
