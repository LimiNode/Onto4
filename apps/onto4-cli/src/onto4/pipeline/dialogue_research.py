"""Bounded multi-turn dialogue research helpers.

This layer records dialogue-stage outcomes separately from semantic scoring and
offers a model-backed isolated refinement adapter.  It does not assign an
Onto4 verdict and it never relaxes the existing replay or provenance checks.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
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
from .decision_bridge import CLARIFICATION_KIND_BY_REFINEMENT
from onto4.reasoning import PipelineDisposition


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
    required_turns: int | None
    admitted_turns: int | None
    answered_turns: int | None
    accepted_refinements: int | None
    completed_reassessments: int | None
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
    """Internal host binding discovered from the question generator.

    ``target_family`` is retained only for in-process oracle validation.  Use
    :meth:`safe_record` when exporting diagnostics.
    """

    case_id: str
    turn_index: int
    kind: str
    target_family: str | None
    target_ids: tuple[str, ...]
    corpus_binding: str | None = None
    snapshot_id: str | None = None
    previous_snapshot_id: str | None = None
    assessment_id: str | None = None

    def safe_record(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "turn_index": self.turn_index,
            "kind": self.kind,
            "target_family": "opaque" if self.target_family else None,
            "target_count": len(self.target_ids),
            "corpus_bound": self.corpus_binding is not None,
            "snapshot_bound": self.snapshot_id is not None,
            "assessment_bound": self.assessment_id is not None,
        }


@dataclass(frozen=True)
class HostQuestionDiscovery:
    """One host preflight result, including assessment/snapshot provenance."""

    questions: tuple[ClarificationQuestion, ...]
    snapshot_id: str
    assessment_id: str
    previous_snapshot_id: str | None = None


def _corpus_binding(corpus: ClarificationCorpus) -> str:
    payload = {
        "name": corpus.name,
        "version": corpus.version,
        "cases": [case.case_id for case in corpus.cases],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def discover_host_question_intents(
    corpus: ClarificationCorpus,
    discover: Callable[[object], HostQuestionDiscovery],
) -> tuple[DiscoveredQuestionIntent, ...]:
    """Run an explicit preflight against host-owned questions.

    The callback is the host assessment/policy boundary.  This function only
    records structural intent; it never rewrites the evaluation oracle.  The
    callback must return a host snapshot/assessment binding; a bare question
    list is rejected rather than being treated as a valid preflight.
    """

    discovered: list[DiscoveredQuestionIntent] = []
    for case in corpus.cases:
        if case.mode != "dialogue":
            continue
        discovered_result = discover(case)
        if isinstance(discovered_result, HostQuestionDiscovery):
            questions = discovered_result.questions
            snapshot_id = discovered_result.snapshot_id
            assessment_id = discovered_result.assessment_id
            previous_snapshot_id = discovered_result.previous_snapshot_id
        else:
            raise ValueError(
                "Host intent discovery must return HostQuestionDiscovery with provenance."
            )
        if len(questions) > 1:
            raise ValueError(
                "Initial preflight accepts one question; use sequential preflight for multi-turn cases."
            )
        for index, question in enumerate(questions):
            discovered.append(
                DiscoveredQuestionIntent(
                    case_id=case.case_id,
                    turn_index=index,
                    kind=question.kind.value,
                    target_family=question.target_family,
                    target_ids=tuple(question.target_ids),
                    corpus_binding=_corpus_binding(corpus),
                    snapshot_id=snapshot_id,
                    previous_snapshot_id=previous_snapshot_id,
                    assessment_id=assessment_id,
                )
            )
    return tuple(discovered)


def discover_sequential_host_question_intents(
    corpus: ClarificationCorpus,
    discover: Callable[[object, int, str | None], HostQuestionDiscovery],
) -> tuple[DiscoveredQuestionIntent, ...]:
    """Discover one host question per reassessed snapshot in sequence.

    ``discover`` receives the case, scripted turn index and the snapshot id
    produced by the previous step.  A result with anything other than one
    question is rejected, so a first-state candidate list cannot masquerade as
    a multi-turn preflight.
    """

    discovered: list[DiscoveredQuestionIntent] = []
    binding = _corpus_binding(corpus)
    for case in corpus.cases:
        if case.mode != "dialogue":
            continue
        expected_count = sum(
            turn.get("role") == "assistant" and "question_kind" in turn
            for turn in case.dialogue
        )
        previous_snapshot: str | None = None
        for turn_index in range(expected_count):
            result = discover(case, turn_index, previous_snapshot)
            if not isinstance(result, HostQuestionDiscovery) or len(result.questions) != 1:
                raise ValueError("Sequential host preflight must return one question per snapshot.")
            question = result.questions[0]
            discovered.append(
                DiscoveredQuestionIntent(
                    case_id=case.case_id,
                    turn_index=turn_index,
                    kind=question.kind.value,
                    target_family=question.target_family,
                    target_ids=tuple(question.target_ids),
                    corpus_binding=binding,
                    snapshot_id=result.snapshot_id,
                    previous_snapshot_id=result.previous_snapshot_id,
                    assessment_id=result.assessment_id,
                )
            )
            previous_snapshot = result.snapshot_id
    return tuple(discovered)


def validate_dialogue_intent_manifest(
    corpus: ClarificationCorpus,
    manifest: Sequence[DiscoveredQuestionIntent],
) -> None:
    """Require a frozen preflight manifest to cover the scripted dialogue."""

    by_case: dict[str, list[DiscoveredQuestionIntent]] = {}
    for item in manifest:
        if item.case_id not in {case.case_id for case in corpus.cases}:
            raise ValueError("Host intent preflight contains a foreign case.")
        if item.corpus_binding != _corpus_binding(corpus):
            raise ValueError("Host intent preflight corpus binding is invalid.")
        if not item.snapshot_id or not item.assessment_id:
            raise ValueError("Host intent preflight lacks assessment/snapshot provenance.")
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
        if len(actual) != len(expected):
            raise ValueError(
                f"Host intent preflight turn count is invalid for case {case.case_id!r}."
            )
        if not actual:
            continue
        if tuple(item.turn_index for item in actual) != tuple(range(len(actual))):
            raise ValueError("Host intent preflight turn indexes are not contiguous.")
        if actual[0].previous_snapshot_id is not None:
            raise ValueError("First host preflight turn must have no predecessor snapshot.")
        if len({item.snapshot_id for item in actual}) != len(actual):
            raise ValueError("Host intent preflight snapshots are duplicated.")
        for previous, current in zip(actual, actual[1:]):
            if current.previous_snapshot_id != previous.snapshot_id:
                raise ValueError("Host intent preflight snapshot sequence is broken.")
        if len({item.assessment_id for item in actual}) != len(actual):
            raise ValueError("Host intent preflight assessment provenance is duplicated.")
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


def _stage_flag(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value > 0
    return None


def _dialogue_status(
    required_turns: int | None,
    admitted_turns: int | None,
    answered_turns: int | None,
    accepted_refinements: int | None,
    completed_reassessments: int | None,
    question_issued: bool | None,
    answer_consumed: bool | None,
    refinement_accepted: bool | None,
    reassessment_performed: bool | None,
) -> str:
    if required_turns is not None:
        counts = (
            admitted_turns,
            answered_turns,
            accepted_refinements,
            completed_reassessments,
        )
        if any(value is None for value in counts):
            return "unverified"
        if any(value < required_turns for value in counts if value is not None):
            return "incomplete"
        return "complete"
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
    required_turns = diagnostics.get("required_turns")
    required_turns = required_turns if isinstance(required_turns, int) else None
    admitted_turns = diagnostics.get("admitted_turns")
    admitted_turns = admitted_turns if isinstance(admitted_turns, int) else None
    answered_turns = diagnostics.get("answered_turns")
    answered_turns = answered_turns if isinstance(answered_turns, int) else None
    accepted_refinements = diagnostics.get("accepted_refinements")
    accepted_refinements = accepted_refinements if isinstance(accepted_refinements, int) else None
    completed_reassessments = diagnostics.get("completed_reassessments")
    completed_reassessments = completed_reassessments if isinstance(completed_reassessments, int) else None
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
        required_turns=required_turns,
        admitted_turns=admitted_turns,
        answered_turns=answered_turns,
        accepted_refinements=accepted_refinements,
        completed_reassessments=completed_reassessments,
        question_issued=question_issued,
        answer_consumed=answer_consumed,
        refinement_accepted=refinement_accepted,
        reassessment_performed=reassessment_performed,
        dialogue_status=_dialogue_status(
            required_turns,
            admitted_turns,
            answered_turns,
            accepted_refinements,
            completed_reassessments,
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
    intent_manifest: Sequence[DiscoveredQuestionIntent] | None = None,
) -> BoundedDialogueResearchRun:
    """Run only dialogue cases while preserving the paired benchmark contract."""

    dialogue_cases = tuple(case for case in corpus.cases if case.mode == "dialogue")
    if not dialogue_cases:
        raise ValueError("Bounded dialogue research requires at least one dialogue case.")
    if intent_manifest is not None:
        validate_dialogue_intent_manifest(corpus, intent_manifest)
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
    assessment_question = session.assessment.ask_result.clarification_question
    if (
        assessment_question is None
        or assessment_question != question
    ):
        raise ValueError("pending question does not match the assessed host question.")
    decision = pending.decision
    decision_result = decision.decision_result
    if (
        decision.issued_question_id != question.id
        or decision.issued_question_kind is not question.kind
        or decision_result.request.state.get("interpretation_id")
        != session.clarification.interpretation.id
        or decision_result.disposition is not PipelineDisposition.AskClarification
        or decision_result.selected_choice not in decision_result.request.choices
        or CLARIFICATION_KIND_BY_REFINEMENT.get(decision_result.selected_choice)
        is not question.kind
    ):
        raise ValueError("pending question provenance is not host-admissible.")
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
    return replace(result, protocol="session_bound_isolated_refinement")


__all__ = [
    "BoundedDialogueResearchRun",
    "DiscoveredQuestionIntent",
    "HostQuestionDiscovery",
    "discover_host_question_intents",
    "discover_sequential_host_question_intents",
    "validate_dialogue_intent_manifest",
    "DialogueResearchCell",
    "run_bounded_dialogue_research",
    "run_model_backed_isolated_refinement_pair",
    "run_session_bound_isolated_refinement_pair",
    "write_dialogue_research_report",
]
