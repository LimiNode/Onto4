"""Bounded multi-turn dialogue research helpers.

This layer records dialogue-stage outcomes separately from semantic scoring and
offers a model-backed isolated refinement adapter.  It does not assign an
Onto4 verdict and it never relaxes the existing replay or provenance checks.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

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
from .orchestration import ReasoningSession


@dataclass(frozen=True)
class DialogueResearchCell:
    """Stage-level observation for one dialogue case and one condition."""

    condition: str
    case_id: str
    outcome: str
    execution_status: str
    question_candidate_generated: bool | None
    question_selected: bool | None
    intent_admitted: bool | None
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


@dataclass(frozen=True)
class DiscoveredQuestionIntent:
    """Privacy-safe binding discovered from the host question generator."""

    case_id: str
    turn_index: int
    kind: str
    target_family: str | None
    target_ids: tuple[str, ...]


def discover_host_question_intents(
    corpus: ClarificationCorpus,
    discover: Callable[[object], Sequence[ClarificationQuestion]],
) -> tuple[DiscoveredQuestionIntent, ...]:
    """Run an explicit preflight against host-owned questions.

    The callback is the host assessment/policy boundary.  This function only
    records structural intent; it never rewrites the evaluation oracle.
    """

    discovered: list[DiscoveredQuestionIntent] = []
    for case in corpus.cases:
        if case.mode != "dialogue":
            continue
        questions = tuple(discover(case))
        for index, question in enumerate(questions):
            discovered.append(
                DiscoveredQuestionIntent(
                    case_id=case.case_id,
                    turn_index=index,
                    kind=question.kind.value,
                    target_family=question.target_family,
                    target_ids=tuple(question.target_ids),
                )
            )
    return tuple(discovered)


def validate_dialogue_intent_manifest(
    corpus: ClarificationCorpus,
    manifest: Sequence[DiscoveredQuestionIntent],
) -> None:
    """Require a frozen preflight manifest to cover the scripted dialogue."""

    by_case: dict[str, list[DiscoveredQuestionIntent]] = {}
    for item in manifest:
        by_case.setdefault(item.case_id, []).append(item)
    for case in corpus.cases:
        if case.mode != "dialogue":
            continue
        expected = tuple(
            turn
            for turn in case.dialogue
            if turn.get("role") == "assistant" and "question_kind" in turn
        )
        actual = tuple(by_case.get(case.case_id, ()))
        if len(actual) < len(expected):
            raise ValueError(
                f"Host intent preflight is incomplete for case {case.case_id!r}."
            )
        for index, turn in enumerate(expected):
            item = actual[index]
            if item.kind != str(turn["question_kind"]):
                raise ValueError("Host intent preflight kind contradicts the corpus.")
            family = turn.get("target_family")
            if family is not None and item.target_family != family:
                raise ValueError("Host intent preflight family contradicts the corpus.")
            target_ids = tuple(turn.get("target_ids", ()))
            if target_ids and item.target_ids != target_ids:
                raise ValueError("Host intent preflight targets contradict the corpus.")


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
        question_candidate_generated=_stage_flag(
            diagnostics.get("question_candidate_generated")
        ),
        question_selected=_stage_flag(diagnostics.get("question_selected")),
        intent_admitted=_stage_flag(diagnostics.get("intent_admitted")),
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
            ("question_candidate_generated", cell.question_candidate_generated),
            ("question_selected", cell.question_selected),
            ("intent_admitted", cell.intent_admitted),
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
                "question_candidate_generated",
                "question_selected",
                "intent_admitted",
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


def run_session_bound_isolated_refinement_pair(
    session: ReasoningSession,
    answer: str,
    *,
    full_snapshot_provider: InterpretationRefinementProvider,
    typed_delta_provider: RefinementDeltaProvider,
    case_id: str = "session-bound-isolated-refinement",
):
    """Compare refinements only for a question issued by the host session.

    Unlike :func:`run_model_backed_isolated_refinement_pair`, this protocol
    does not accept an arbitrary question.  It requires a live assessment and
    an immutable ``PendingClarification`` bound to that exact interpretation.
    """

    if session.assessment is None:
        raise ValueError("session-bound refinement requires a current assessment.")
    pending = session.clarification.pending
    if pending is None:
        raise ValueError("session-bound refinement requires a host-issued pending question.")
    if pending.interpretation != session.clarification.interpretation:
        raise ValueError("pending question is not bound to the session interpretation.")
    if session.assessment.interpretation != session.clarification.interpretation:
        raise ValueError("assessment is not bound to the session interpretation.")
    question = pending.decision.question
    if question is None:
        raise ValueError("host-issued pending clarification has no question.")
    return _run_session_bound_pair(
        session.clarification.interpretation,
        question,
        answer,
        full_snapshot_provider=full_snapshot_provider,
        typed_delta_provider=typed_delta_provider,
        case_id=case_id,
    )


def _run_session_bound_pair(
    initial: InterpretationSpace,
    question: ClarificationQuestion,
    answer: str,
    *,
    full_snapshot_provider: InterpretationRefinementProvider,
    typed_delta_provider: RefinementDeltaProvider,
    case_id: str,
):
    result = run_model_backed_isolated_refinement_pair(
        initial,
        question,
        answer,
        full_snapshot_provider=full_snapshot_provider,
        typed_delta_provider=typed_delta_provider,
        case_id=case_id,
    )
    # The underlying pair validates transition provenance; this explicit
    # marker prevents callers from confusing it with an unbound provider pair.
    return type(result)(
        case_id=result.case_id,
        initial_interpretation_id=result.initial_interpretation_id,
        question_id=result.question_id,
        answer=result.answer,
        initial_snapshot_digest=result.initial_snapshot_digest,
        cells=result.cells,
        protocol="session_bound_isolated_refinement",
    )


__all__ = [
    "BoundedDialogueResearchRun",
    "DiscoveredQuestionIntent",
    "discover_host_question_intents",
    "validate_dialogue_intent_manifest",
    "DialogueResearchCell",
    "run_bounded_dialogue_research",
    "run_model_backed_isolated_refinement_pair",
    "run_session_bound_isolated_refinement_pair",
    "write_dialogue_research_report",
]
