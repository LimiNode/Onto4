"""Controlled paired A/B benchmark and isolated refinement protocol."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping

from onto4.reasoning import ClarificationQuestion, ClarificationTurn, InterpretationSpace

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
_REQUIRED_CONDITION_NAMES = frozenset({"A1", "A2", "B1", "B2"})
_EXPECTED_CONDITION_MODES = {
    "A1": ("context_late", "full_snapshot"),
    "A2": ("context_aware", "full_snapshot"),
    "B1": ("context_late", "typed_delta"),
    "B2": ("context_aware", "typed_delta"),
}
_RECEIPT_MANIFEST_SCHEMA_VERSION = 2
_FAILED_OUTCOMES = frozenset(
    {
        EvaluationOutcome.TRANSPORT_ERROR,
        EvaluationOutcome.REQUEST_TIMEOUT,
        EvaluationOutcome.CASE_DEADLINE_EXCEEDED,
        EvaluationOutcome.EMPTY_CONTENT,
        EvaluationOutcome.JSON_INVALID,
        EvaluationOutcome.SCHEMA_INVALID,
        EvaluationOutcome.PROVENANCE_INVALID,
        EvaluationOutcome.CONTEXT_UNAVAILABLE,
        EvaluationOutcome.QUESTION_INTENT_MISMATCH,
        EvaluationOutcome.QUESTION_INTENT_UNVERIFIED,
    }
)
_INCOMPLETE_OUTCOMES = frozenset(
    {
        EvaluationOutcome.DIALOGUE_INCOMPLETE,
        EvaluationOutcome.SCRIPT_EXHAUSTED,
    }
)
_UNSUPPORTED_OUTCOMES = frozenset({EvaluationOutcome.UNSUPPORTED_DIALOGUE_STEP})


class BenchmarkStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNVERIFIED = "unverified"
    NOT_COMPARABLE = "not_comparable"


class ExecutionStatus(str, Enum):
    SUCCESSFUL = "successful"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"


class ReceiptProvenanceError(ValueError):
    """Receipt artifacts cannot be trusted for paired re-scoring."""


def _scripted_question_intents(
    case: ClarificationCorpusCase,
) -> tuple[tuple[str | None, str | None, tuple[str, ...] | None], ...]:
    """Extract the host-owned question contract from the public dialogue script."""

    intents: list[tuple[str | None, str | None, tuple[str, ...] | None]] = []
    for turn in case.dialogue:
        if turn.get("role") != "assistant":
            continue
        if not any(key in turn for key in ("question_kind", "target_family", "target_ids")):
            continue
        raw_ids = turn.get("target_ids")
        target_ids = (
            tuple(raw_ids)
            if isinstance(raw_ids, list)
            and all(isinstance(item, str) and item for item in raw_ids)
            else None
        )
        intents.append(
            (
                turn.get("question_kind") if isinstance(turn.get("question_kind"), str) else None,
                turn.get("target_family") if isinstance(turn.get("target_family"), str) else None,
                target_ids,
            )
        )
    return tuple(intents)


def _target_family_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _scripted_question_records_status(
    case: ClarificationCorpusCase,
    diagnostics: Mapping[str, object],
) -> bool | None:
    """Compare every recorded question with the immutable corpus script.

    ``None`` means that required evidence is missing; ``False`` means a
    present, comparable record demonstrably contradicts the script.
    """

    expected = _scripted_question_intents(case)
    records = diagnostics.get("question_records")
    if not expected:
        return None
    if not isinstance(records, list):
        return None
    if len(records) > len(expected):
        return False
    if len(records) < len(expected):
        return None
    for index, (expected_kind, expected_family, expected_ids) in enumerate(expected):
        record = records[index]
        if not isinstance(record, Mapping):
            return None
        if record.get("turn_index") != index:
            return False
        actual_kind = record.get("question_kind")
        actual_ids = record.get("question_target_ids")
        if expected_kind is None or expected_family is None or expected_ids is None:
            return None
        family_match = record.get("question_script_target_family_match")
        family_digest = record.get("question_target_family_digest")
        if actual_kind is None or actual_ids is None or family_match is None:
            return None
        if family_match is not True:
            return False
        if actual_kind != expected_kind:
            return False
        if family_digest is None:
            return None
        if family_digest != _target_family_digest(expected_family):
            return False
        if tuple(actual_ids) != expected_ids:
            return False
    return True


@dataclass(frozen=True)
class BenchmarkCondition:
    """One cell in the frozen 2x2 interpretation/refinement design."""

    name: str
    interpretation_context_mode: str
    refinement_mode: str

    def __post_init__(self) -> None:
        if self.name not in _REQUIRED_CONDITION_NAMES:
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
    execution_status: str
    workflow_status: str
    semantic_status: str
    semantic_verdict: str | None
    clarification_turns: int | None
    clarification_turns_known: bool
    provider_calls: int
    completion_tokens: int
    elapsed_seconds: float
    workflow_diagnostics: Mapping[str, object]


@dataclass(frozen=True)
class PairedBenchmarkSummary:
    total_cases: int
    oracle_comparable_observations: int
    oracle_passed_observations: int
    semantic_errors: int
    operational_failures: int
    execution_counts: Mapping[str, Mapping[str, int]]
    workflow_counts: Mapping[str, Mapping[str, int]]
    semantic_counts: Mapping[str, Mapping[str, int]]
    success_denominators: Mapping[str, int]
    clarification_turns: Mapping[str, int | None]
    clarification_turns_known_cases: Mapping[str, int]
    provider_calls: Mapping[str, int]
    completion_tokens: Mapping[str, int]
    estimated_output_cost_usd: Mapping[str, float | None]
    elapsed_seconds: Mapping[str, float]
    pair_wins: Mapping[str, Mapping[str, int]]


@dataclass(frozen=True)
class PairedBenchmarkRun:
    corpus_name: str
    corpus_version: int
    corpus_digest: str
    conditions: tuple[BenchmarkCondition, ...]
    runs: Mapping[str, EvaluationRun]
    run_configs: Mapping[str, EvaluationConfig]
    metadata: Mapping[str, object]
    cells: tuple[BenchmarkCell, ...]
    summary: PairedBenchmarkSummary


@dataclass(frozen=True)
class IsolatedRefinementCell:
    mode: str
    outcome: str
    transition_valid: bool
    successor_interpretation_id: str | None
    semantic_obligation_digest: str | None
    semantic_obligations: tuple[str, ...]
    error_code: str | None


@dataclass(frozen=True)
class IsolatedRefinementRun:
    case_id: str
    initial_interpretation_id: str
    question_id: str
    answer: str
    initial_snapshot_digest: str
    cells: tuple[IsolatedRefinementCell, ...]
    protocol: str = "provider_isolated_refinement"


def _execution_status(outcome: EvaluationOutcome) -> ExecutionStatus:
    if outcome in _FAILED_OUTCOMES:
        return ExecutionStatus.FAILED
    if outcome in _INCOMPLETE_OUTCOMES:
        return ExecutionStatus.INCOMPLETE
    if outcome in _UNSUPPORTED_OUTCOMES:
        return ExecutionStatus.UNSUPPORTED
    return ExecutionStatus.SUCCESSFUL


def _workflow_status(
    case: ClarificationCorpusCase,
    receipt: CaseReceipt,
) -> BenchmarkStatus:
    checks: list[bool | None] = []
    expected_after = case.expected_after_answer
    expected_disposition = expected_after.get("disposition")
    if isinstance(expected_disposition, str):
        diagnostics = receipt.diagnostics
        if expected_disposition == "complete":
            reassessed = diagnostics.get("reassessment_performed")
            checks.append(
                None
                if reassessed is None
                else (
                    receipt.outcome is EvaluationOutcome.ASSESSMENT_COMPLETED
                    and bool(reassessed)
                )
            )
        elif expected_disposition == "clarification_required":
            checks.append(receipt.outcome is EvaluationOutcome.CLARIFICATION_REQUESTED)
        elif expected_disposition == "dialogue_reassessment_required":
            expected_intents = _scripted_question_intents(case)
            expected_turn_count = len(expected_intents)
            required_turns = diagnostics.get("required_turns")
            counters = (
                diagnostics.get("questions_issued"),
                diagnostics.get("answers_consumed"),
                diagnostics.get("admitted_turns"),
                diagnostics.get("answered_turns"),
                diagnostics.get("accepted_refinements"),
                diagnostics.get("completed_reassessments"),
            )
            required = counters + (
                diagnostics.get("refinement_accepted"),
                diagnostics.get("reassessment_performed"),
            )
            record_status = _scripted_question_records_status(case, diagnostics)
            if receipt.outcome in {
                EvaluationOutcome.DIALOGUE_INCOMPLETE,
                EvaluationOutcome.SCRIPT_EXHAUSTED,
            }:
                checks.append(False)
            elif not expected_intents:
                checks.append(None)
            elif any(value is None for value in required):
                checks.append(None)
            elif any(type(value) is not int for value in counters):
                checks.append(None)
            elif type(required_turns) is not int:
                checks.append(None)
            elif required_turns != expected_turn_count:
                checks.append(False)
            elif record_status is None:
                checks.append(None)
            else:
                checks.append(
                    (
                    receipt.outcome in {
                        EvaluationOutcome.ASSESSMENT_COMPLETED,
                        EvaluationOutcome.NEED_EVIDENCE,
                        EvaluationOutcome.CANNOT_PROCEED,
                    }
                    and all(int(value) >= required_turns for value in counters)
                    and bool(required[-2])
                    and bool(required[-1])
                    and record_status
                    )
                )
        else:
            checks.append(None)

    expected_clarification = case.expected_clarification
    if isinstance(expected_clarification, Mapping):
        expected_kind = expected_clarification.get("kind")
        records = receipt.diagnostics.get("question_records")
        first_record = records[0] if isinstance(records, list) and records else None
        if case.mode == "dialogue" and first_record is None:
            observed_kind = None
            observed_match = None
        else:
            observed_kind = (
                first_record.get("question_kind")
                if isinstance(first_record, Mapping)
                else receipt.diagnostics.get("question_kind")
            )
            observed_match = (
                first_record.get("question_target_family_match")
                if isinstance(first_record, Mapping)
                else receipt.diagnostics.get("question_target_family_match")
            )
        if isinstance(expected_kind, str):
            checks.append(
                observed_kind == expected_kind if observed_kind is not None else None
            )
        expected_target_family = expected_clarification.get("target_family")
        if isinstance(expected_target_family, str):
            checks.append(observed_match if isinstance(observed_match, bool) else None)

    if not checks:
        return BenchmarkStatus.NOT_COMPARABLE
    if any(check is False for check in checks):
        return BenchmarkStatus.INCORRECT
    if any(check is None for check in checks):
        return BenchmarkStatus.UNVERIFIED
    return BenchmarkStatus.CORRECT


def _semantic_status(
    case: ClarificationCorpusCase,
    receipt: CaseReceipt,
    execution: ExecutionStatus,
) -> BenchmarkStatus:
    expected_verdict = case.expected_after_answer.get("verdict")
    if not isinstance(expected_verdict, str):
        return BenchmarkStatus.NOT_COMPARABLE
    if execution is not ExecutionStatus.SUCCESSFUL:
        return BenchmarkStatus.UNVERIFIED
    if receipt.semantic_verdict is None:
        return BenchmarkStatus.UNVERIFIED
    return (
        BenchmarkStatus.CORRECT
        if receipt.semantic_verdict == expected_verdict
        else BenchmarkStatus.INCORRECT
    )


def _completion_tokens(receipt: CaseReceipt) -> int:
    return sum(
        int(match.group("tokens"))
        for detail in receipt.provider_stage_details.values()
        for match in _COMPLETION_TOKENS.finditer(str(detail))
    )


def _cell(
    condition: BenchmarkCondition,
    case: ClarificationCorpusCase,
    receipt: CaseReceipt,
) -> BenchmarkCell:
    execution = _execution_status(receipt.outcome)
    known = bool(receipt.diagnostics.get("clarification_turns_known"))
    turns = (
        int(receipt.diagnostics["clarification_turns"])
        if known and isinstance(receipt.diagnostics.get("clarification_turns"), int)
        else None
    )
    diagnostic_keys = {
        "detail_code",
        "question_candidate_generated",
        "question_candidate_count",
        "question_selected",
        "intent_admitted",
        "required_turns",
        "admitted_turns",
        "answered_turns",
        "accepted_refinements",
        "completed_reassessments",
        "question_intent_failure_reason",
        "unsupported_transition",
        "last_stage",
        "questions_issued",
        "answers_consumed",
        "question_id",
        "question_kind",
        "question_target_family",
        "question_target_family_digest",
        "question_target_family_match",
        "question_target_ids",
        "question_records",
        "refinement_accepted",
        "reassessment_performed",
        "clarification_turns_known",
    }
    diagnostics = {
        key: receipt.diagnostics[key]
        for key in diagnostic_keys
        if key in receipt.diagnostics
    }
    if receipt.detail_code is not None:
        diagnostics["detail_code"] = receipt.detail_code
    return BenchmarkCell(
        condition=condition.name,
        case_id=case.case_id,
        outcome=receipt.outcome.value,
        execution_status=execution.value,
        workflow_status=_workflow_status(case, receipt).value,
        semantic_status=_semantic_status(case, receipt, execution).value,
        semantic_verdict=receipt.semantic_verdict,
        clarification_turns=turns,
        clarification_turns_known=known,
        provider_calls=receipt.provider_calls,
        completion_tokens=_completion_tokens(receipt),
        elapsed_seconds=receipt.elapsed_seconds,
        workflow_diagnostics=diagnostics,
    )


def _empty_counts(conditions: tuple[BenchmarkCondition, ...]) -> dict[str, dict[str, int]]:
    return {condition.name: {} for condition in conditions}


def _increment(mapping: dict[str, dict[str, int]], condition: str, value: str) -> None:
    bucket = mapping[condition]
    bucket[value] = bucket.get(value, 0) + 1


def _summary(
    conditions: tuple[BenchmarkCondition, ...],
    cells: tuple[BenchmarkCell, ...],
    *,
    output_cost_per_million: float | None,
) -> PairedBenchmarkSummary:
    execution_counts = _empty_counts(conditions)
    workflow_counts = _empty_counts(conditions)
    semantic_counts = _empty_counts(conditions)
    clarification_totals: dict[str, int] = {condition.name: 0 for condition in conditions}
    clarification_turns: dict[str, int | None] = {condition.name: 0 for condition in conditions}
    clarification_known: dict[str, int] = {condition.name: 0 for condition in conditions}
    clarification_unknown: set[str] = set()
    provider_calls = {condition.name: 0 for condition in conditions}
    completion_tokens = {condition.name: 0 for condition in conditions}
    estimated_cost = {
        condition.name: (
            0.0 if output_cost_per_million is not None else None
        )
        for condition in conditions
    }
    elapsed_seconds = {condition.name: 0.0 for condition in conditions}
    oracle_observations = 0
    oracle_passed = 0
    semantic_errors = 0
    operational_failures = 0
    for cell in cells:
        _increment(execution_counts, cell.condition, cell.execution_status)
        _increment(workflow_counts, cell.condition, cell.workflow_status)
        _increment(semantic_counts, cell.condition, cell.semantic_status)
        provider_calls[cell.condition] += cell.provider_calls
        completion_tokens[cell.condition] += cell.completion_tokens
        elapsed_seconds[cell.condition] += cell.elapsed_seconds
        if cell.clarification_turns_known and cell.clarification_turns is not None:
            clarification_known[cell.condition] += 1
            clarification_totals[cell.condition] += cell.clarification_turns
        else:
            clarification_unknown.add(cell.condition)
        if estimated_cost[cell.condition] is not None:
            estimated_cost[cell.condition] += (
                cell.completion_tokens * output_cost_per_million / 1_000_000
            )
        if cell.semantic_status == BenchmarkStatus.CORRECT.value:
            oracle_observations += 1
            oracle_passed += 1
        elif cell.semantic_status == BenchmarkStatus.INCORRECT.value:
            oracle_observations += 1
            semantic_errors += 1
        if cell.execution_status in {
            ExecutionStatus.FAILED.value,
            ExecutionStatus.UNSUPPORTED.value,
        }:
            operational_failures += 1

    pair_wins = {
        pair: {left: 0, right: 0, "tie": 0}
        for pair, left, right in (
            ("A1_vs_B1", "A1", "B1"),
            ("A2_vs_B2", "A2", "B2"),
            ("A1_vs_A2", "A1", "A2"),
            ("B1_vs_B2", "B1", "B2"),
        )
    }
    by_case: dict[str, dict[str, BenchmarkCell]] = {}
    for cell in cells:
        by_case.setdefault(cell.case_id, {})[cell.condition] = cell
    for case_cells in by_case.values():
        for pair_name, left_name, right_name in (
            ("A1_vs_B1", "A1", "B1"),
            ("A2_vs_B2", "A2", "B2"),
            ("A1_vs_A2", "A1", "A2"),
            ("B1_vs_B2", "B1", "B2"),
        ):
            left, right = case_cells.get(left_name), case_cells.get(right_name)
            if left is None or right is None:
                continue
            comparable = {
                BenchmarkStatus.CORRECT.value,
                BenchmarkStatus.INCORRECT.value,
            }
            if left.semantic_status not in comparable or right.semantic_status not in comparable:
                continue
            if left.semantic_status == right.semantic_status:
                pair_wins[pair_name]["tie"] += 1
            elif left.semantic_status == BenchmarkStatus.CORRECT.value:
                pair_wins[pair_name][left_name] += 1
            else:
                pair_wins[pair_name][right_name] += 1
    for condition in conditions:
        if condition.name in clarification_unknown:
            clarification_turns[condition.name] = None
        else:
            clarification_turns[condition.name] = clarification_totals[condition.name]
    return PairedBenchmarkSummary(
        total_cases=len(by_case),
        oracle_comparable_observations=oracle_observations,
        oracle_passed_observations=oracle_passed,
        semantic_errors=semantic_errors,
        operational_failures=operational_failures,
        execution_counts=execution_counts,
        workflow_counts=workflow_counts,
        semantic_counts=semantic_counts,
        success_denominators={
            condition.name: sum(
                1
                for cell in cells
                if cell.condition == condition.name
                and cell.execution_status == ExecutionStatus.SUCCESSFUL.value
            )
            for condition in conditions
        },
        clarification_turns=clarification_turns,
        clarification_turns_known_cases=clarification_known,
        provider_calls=provider_calls,
        completion_tokens=completion_tokens,
        estimated_output_cost_usd=estimated_cost,
        elapsed_seconds=elapsed_seconds,
        pair_wins=pair_wins,
    )


def _validate_conditions(conditions: tuple[BenchmarkCondition, ...]) -> None:
    names = tuple(condition.name for condition in conditions)
    if set(names) != _REQUIRED_CONDITION_NAMES or len(names) != len(_REQUIRED_CONDITION_NAMES):
        raise ValueError("The paired E2E benchmark requires exactly A1, A2, B1 and B2.")
    for condition in conditions:
        expected = _EXPECTED_CONDITION_MODES[condition.name]
        actual = (condition.interpretation_context_mode, condition.refinement_mode)
        if actual != expected:
            raise ValueError(
                f"Condition {condition.name} has {actual!r}; expected {expected!r}."
            )


def _paired_run_id(
    config: EvaluationConfig,
    artifact_dir: Path | None,
    conditions: tuple[BenchmarkCondition, ...],
) -> str:
    """Resolve one run identity for all cells, preserving an existing resume."""

    if config.run_id is not None:
        if not isinstance(config.run_id, str) or not config.run_id.strip():
            raise ValueError("paired benchmark run_id must be a non-empty string.")
        return config.run_id
    if artifact_dir is not None:
        existing_ids: set[str] = set()
        for condition in conditions:
            receipt_path = artifact_dir / f"{condition.name}.receipts.jsonl"
            if not receipt_path.exists():
                continue
            try:
                manifest = json.loads(receipt_path.read_text(encoding="utf-8").splitlines()[0])
                existing = manifest.get("config", {}).get("run_id")
            except (OSError, IndexError, json.JSONDecodeError, AttributeError):
                existing = None
            if isinstance(existing, str) and existing.strip():
                existing_ids.add(existing)
        if len(existing_ids) > 1:
            raise ValueError("Existing paired receipts disagree on run_id.")
        if existing_ids:
            return next(iter(existing_ids))
    return f"paired-{uuid.uuid4().hex}"


def run_paired_benchmark(
    corpus: ClarificationCorpus,
    *,
    executor_factory: Callable[[BenchmarkCondition], CaseExecutor],
    config: EvaluationConfig,
    receipt_dir: str | Path | None = None,
    output_cost_per_million: float | None = None,
    conditions: tuple[BenchmarkCondition, ...] = DEFAULT_BENCHMARK_CONDITIONS,
    metadata: Mapping[str, object] | None = None,
) -> PairedBenchmarkRun:
    """Run the E2E paired-by-case 2x2 benchmark.

    The four conditions share a corpus and case IDs, but this runner does not
    claim that their initial model-produced InterpretationSpace snapshots are
    identical. Use ``run_isolated_refinement_pair`` for that comparison.
    """

    _validate_conditions(conditions)
    if output_cost_per_million is not None and output_cost_per_million < 0:
        raise ValueError("output_cost_per_million must not be negative.")
    digest = corpus_digest_for_loaded(corpus)
    runs: dict[str, EvaluationRun] = {}
    run_configs: dict[str, EvaluationConfig] = {}
    cells: list[BenchmarkCell] = []
    artifact_dir = Path(receipt_dir) if receipt_dir is not None else None
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    paired_run_id = _paired_run_id(config, artifact_dir, conditions)
    for condition in conditions:
        condition_config = replace(
            config,
            run_id=paired_run_id,
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
        run_configs[condition.name] = condition_config
        by_id = {receipt.case_id: receipt for receipt in result.receipts}
        cells.extend(_cell(condition, case, by_id[case.case_id]) for case in corpus.cases)
    cell_tuple = tuple(cells)
    report_metadata = dict(metadata or {})
    report_metadata.setdefault("benchmark_type", "e2e_paired_by_case")
    report_metadata.setdefault("condition_order", [condition.name for condition in conditions])
    report_metadata.setdefault(
        "output_cost_status",
        "priced" if output_cost_per_million is not None else "not_priced",
    )
    report_metadata.setdefault("output_cost_per_million", output_cost_per_million)
    report_metadata.setdefault("target_catalog_version", config.target_catalog_version)
    report_metadata.setdefault("target_catalog_digest", config.target_catalog_digest)
    return PairedBenchmarkRun(
        corpus_name=corpus.name,
        corpus_version=corpus.version,
        corpus_digest=digest,
        conditions=conditions,
        runs=runs,
        run_configs=run_configs,
        metadata=report_metadata,
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
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=list).encode("utf-8")
    ).hexdigest()


def _semantic_obligation_payload(interpretation: InterpretationSpace) -> dict[str, object]:
    presupposition_by_id = {
        item.id: " ".join(item.description.split()).casefold()
        for item in interpretation.presuppositions
    }
    return {
        "source_text": interpretation.source_text,
        "conceptual_depth": interpretation.conceptual_depth.value,
        "ambiguities": [
            {"term": item.term, "description": item.description}
            for item in interpretation.ambiguities
        ],
        "presuppositions": [{"description": item.description} for item in interpretation.presuppositions],
        "ontologies": [
            {"label": item.label, "description": item.description}
            for item in interpretation.ontologies
        ],
        "readings": [
            {
                "label": item.label,
                "description": item.description,
                "presupposition_count": len(item.presupposition_ids),
                "presupposition_signatures": [
                    presupposition_by_id.get(item_id, f"missing:{item_id}")
                    for item_id in item.presupposition_ids
                ],
            }
            for item in interpretation.readings
        ],
    }


def _semantic_obligations(interpretation: InterpretationSpace) -> tuple[str, ...]:
    payload = _semantic_obligation_payload(interpretation)
    return tuple(
        json.dumps({key: value}, ensure_ascii=False, sort_keys=True)
        for key, value in payload.items()
        if key != "source_text" and key != "conceptual_depth"
    )


def _snapshot_digest(interpretation: InterpretationSpace) -> str:
    return hashlib.sha256(
        json.dumps(
            _semantic_obligation_payload(interpretation),
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def run_isolated_refinement_pair(
    initial: InterpretationSpace,
    question: ClarificationQuestion,
    answer: str,
    *,
    full_snapshot: Callable[
        [InterpretationSpace, ClarificationQuestion, str], tuple[InterpretationSpace, ClarificationTurn]
    ],
    typed_delta: Callable[
        [InterpretationSpace, ClarificationQuestion, str], tuple[InterpretationSpace, ClarificationTurn]
    ],
    case_id: str = "isolated-refinement",
) -> IsolatedRefinementRun:
    """Compare two refinement protocols from one immutable initial snapshot."""

    if not answer.strip():
        raise ValueError("isolated refinement answer must not be empty.")
    known_ids = {
        item.id
        for items in (
            initial.ambiguities,
            initial.presuppositions,
            initial.ontologies,
            initial.readings,
        )
        for item in items
    }
    if any(target_id not in known_ids for target_id in question.target_ids):
        raise ValueError("isolated refinement question targets an unknown initial item.")
    initial_digest = _snapshot_digest(initial)

    def invoke(
        mode: str,
        operation: Callable[
            [InterpretationSpace, ClarificationQuestion, str], tuple[InterpretationSpace, ClarificationTurn]
        ],
    ) -> IsolatedRefinementCell:
        try:
            successor, turn = operation(initial, question, answer)
            if turn.previous_interpretation_id != initial.id:
                raise ValueError("previous interpretation provenance mismatch")
            if turn.question_id != question.id:
                raise ValueError("question provenance mismatch")
            if turn.successor_interpretation_id != successor.id:
                raise ValueError("successor provenance mismatch")
            obligations = _semantic_obligations(successor)
            return IsolatedRefinementCell(
                mode=mode,
                outcome="accepted",
                transition_valid=True,
                successor_interpretation_id=successor.id,
                semantic_obligation_digest=_snapshot_digest(successor),
                semantic_obligations=obligations,
                error_code=None,
            )
        except Exception as exc:  # protocol report must remain per-cell and safe
            return IsolatedRefinementCell(
                mode=mode,
                outcome="failed",
                transition_valid=False,
                successor_interpretation_id=None,
                semantic_obligation_digest=None,
                semantic_obligations=(),
                error_code=type(exc).__name__,
            )

    return IsolatedRefinementRun(
        case_id=case_id,
        initial_interpretation_id=initial.id,
        question_id=question.id,
        answer=answer,
        initial_snapshot_digest=initial_digest,
        cells=(invoke("full_snapshot", full_snapshot), invoke("typed_delta", typed_delta)),
    )


def write_benchmark_report(run: PairedBenchmarkRun, path: str | Path) -> None:
    target = Path(path)
    payload = {
        "record_type": "benchmark_report",
        "benchmark_type": run.metadata.get("benchmark_type", "e2e_paired_by_case"),
        "metadata": dict(run.metadata),
        "corpus_name": run.corpus_name,
        "corpus_version": run.corpus_version,
        "corpus_digest": run.corpus_digest,
        "conditions": [asdict(condition) for condition in run.conditions],
        "run_configs": {name: asdict(config) for name, config in run.run_configs.items()},
        "summary": asdict(run.summary),
        "cells": [asdict(cell) for cell in run.cells],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


_PROVENANCE_CONFIG_FIELDS = (
    "provider",
    "model",
    "mode",
    "prompt_version",
    "prompt_hash",
    "commit_sha",
    "model_artifact_digest",
    "temperature",
    "thinking_enabled",
    "max_output_tokens",
    "prompt_variant",
    "requested_conceptual_depth",
    "run_id",
    "context_profile_digests",
    "request_timeout_seconds",
    "case_deadline_seconds",
    "inter_case_delay_seconds",
    "max_retries",
)


def _load_receipt_file(
    path: Path,
) -> tuple[Mapping[str, object], EvaluationConfig, tuple[CaseReceipt, ...]]:
    if not path.exists():
        raise ReceiptProvenanceError(f"Receipt file {path} does not exist.")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ReceiptProvenanceError(f"Receipt file {path} is empty.")
    manifest = json.loads(lines[0])
    if not isinstance(manifest, Mapping):
        raise ReceiptProvenanceError(f"Receipt file {path} has no usable manifest.")
    if manifest.get("manifest_schema_version") != _RECEIPT_MANIFEST_SCHEMA_VERSION:
        raise ReceiptProvenanceError(
            f"Receipt file {path} is legacy or missing manifest metadata "
            "(legacy_missing_metadata)."
        )
    if manifest.get("record_type") != "manifest":
        raise ReceiptProvenanceError(f"Receipt file {path} has an invalid manifest record type.")
    if not isinstance(manifest.get("config"), Mapping):
        raise ReceiptProvenanceError(f"Receipt file {path} has no usable manifest config.")
    for key in ("corpus_name", "corpus_version", "corpus_digest"):
        if key not in manifest:
            raise ReceiptProvenanceError(f"Receipt file {path} is missing {key} metadata.")
    config = EvaluationConfig(**dict(manifest["config"]))
    receipts: list[CaseReceipt] = []
    seen_ids: set[str] = set()
    for line in lines[1:]:
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, Mapping) or item.get("record_type") == "manifest":
            raise ReceiptProvenanceError(f"Receipt file {path} contains an invalid receipt record.")
        case_id = str(item["case_id"])
        if case_id in seen_ids:
            raise ReceiptProvenanceError(f"Receipt file {path} contains duplicate case_id {case_id!r}.")
        seen_ids.add(case_id)
        receipts.append(
            CaseReceipt(
                case_id=case_id,
                case_mode=str(item.get("case_mode", "single_pass")),
                outcome=EvaluationOutcome(item["outcome"]),
                elapsed_seconds=float(item.get("elapsed_seconds", 0.0)),
                provider_stage_seconds=item.get("provider_stage_seconds", {}),
                provider_stage_outcomes=item.get("provider_stage_outcomes", {}),
                provider_stage_details=item.get("provider_stage_details", {}),
                provider_calls=int(item.get("provider_calls", 0)),
                semantic_verdict=item.get("semantic_verdict"),
                detail_code=item.get("detail_code"),
                diagnostics=item.get("diagnostics", {}),
            )
        )
    return manifest, config, tuple(receipts)


def rescore_paired_receipts(
    corpus: ClarificationCorpus,
    receipt_dir: str | Path,
    *,
    conditions: tuple[BenchmarkCondition, ...] = DEFAULT_BENCHMARK_CONDITIONS,
    output_cost_per_million: float | None = None,
    metadata: Mapping[str, object] | None = None,
) -> PairedBenchmarkRun:
    """Re-score existing safe receipts without calling a provider again."""

    _validate_conditions(conditions)
    root = Path(receipt_dir)
    digest = corpus_digest_for_loaded(corpus)
    runs: dict[str, EvaluationRun] = {}
    configs: dict[str, EvaluationConfig] = {}
    cells: list[BenchmarkCell] = []
    manifests: dict[str, Mapping[str, object]] = {}
    expected_case_ids = {case.case_id for case in corpus.cases}
    for condition in conditions:
        manifest, config, receipts = _load_receipt_file(root / f"{condition.name}.receipts.jsonl")
        manifests[condition.name] = manifest
        if manifest.get("corpus_digest") != digest:
            raise ReceiptProvenanceError(
                f"Receipt file for {condition.name} has a corpus digest mismatch."
            )
        if manifest.get("corpus_name") != corpus.name or manifest.get("corpus_version") != corpus.version:
            raise ReceiptProvenanceError(
                f"Receipt file for {condition.name} has corpus metadata mismatch."
            )
        expected_modes = _EXPECTED_CONDITION_MODES[condition.name]
        if config.variant != condition.name or (
            config.interpretation_context_mode,
            config.refinement_mode,
        ) != expected_modes:
            raise ReceiptProvenanceError(
                f"Receipt file for {condition.name} has condition provenance mismatch."
            )
        configs[condition.name] = config
        by_id = {receipt.case_id: receipt for receipt in receipts}
        foreign = sorted(set(by_id) - expected_case_ids)
        if foreign:
            raise ReceiptProvenanceError(
                f"Receipt file for {condition.name} has foreign cases: {', '.join(foreign)}"
            )
        missing = [case.case_id for case in corpus.cases if case.case_id not in by_id]
        if missing:
            raise ReceiptProvenanceError(
                f"Receipt file for {condition.name} is missing cases: {', '.join(missing)}"
            )
        cells.extend(_cell(condition, case, by_id[case.case_id]) for case in corpus.cases)
    baseline = manifests[conditions[0].name]
    baseline_config = configs[conditions[0].name]
    if not isinstance(baseline_config.run_id, str) or not baseline_config.run_id.strip():
        raise ReceiptProvenanceError(
            "Paired receipt manifests have no non-empty run_id provenance."
        )
    for condition in conditions[1:]:
        config = configs[condition.name]
        for field_name in _PROVENANCE_CONFIG_FIELDS:
            if getattr(config, field_name) != getattr(baseline_config, field_name):
                raise ReceiptProvenanceError(
                    f"Receipt manifests disagree on shared configuration {field_name!r}."
                )
        for key in ("corpus_name", "corpus_version", "corpus_digest"):
            if manifests[condition.name].get(key) != baseline.get(key):
                raise ReceiptProvenanceError(
                    f"Receipt manifests disagree on shared corpus metadata {key!r}."
                )
    report_metadata = dict(metadata or {})
    report_metadata.setdefault("benchmark_type", "e2e_paired_by_case_rescore")
    report_metadata.setdefault("condition_order", [condition.name for condition in conditions])
    report_metadata.setdefault(
        "output_cost_status",
        "priced" if output_cost_per_million is not None else "not_priced",
    )
    report_metadata.setdefault("output_cost_per_million", output_cost_per_million)
    report_metadata.setdefault("target_catalog_version", baseline_config.target_catalog_version)
    report_metadata.setdefault("target_catalog_digest", baseline_config.target_catalog_digest)
    cell_tuple = tuple(cells)
    return PairedBenchmarkRun(
        corpus_name=corpus.name,
        corpus_version=corpus.version,
        corpus_digest=digest,
        conditions=conditions,
        runs=runs,
        run_configs=configs,
        metadata=report_metadata,
        cells=cell_tuple,
        summary=_summary(
            conditions,
            cell_tuple,
            output_cost_per_million=output_cost_per_million,
        ),
    )


def write_benchmark_diagnostics(run: PairedBenchmarkRun, path: str | Path) -> None:
    """Write safe per-case diagnostics without prompts or model payloads."""

    target = Path(path)
    payload = {
        "record_type": "benchmark_diagnostics",
        "benchmark_type": run.metadata.get("benchmark_type", "e2e_paired_by_case"),
        "corpus_digest": run.corpus_digest,
        "conditions": [condition.name for condition in run.conditions],
        "cases": [
            {
                "condition": cell.condition,
                "case_id": cell.case_id,
                "outcome": cell.outcome,
                "execution_status": cell.execution_status,
                "workflow_status": cell.workflow_status,
                "semantic_status": cell.semantic_status,
                "provider_calls": cell.provider_calls,
                "clarification_turns": cell.clarification_turns,
                "clarification_turns_known": cell.clarification_turns_known,
                "workflow_diagnostics": dict(cell.workflow_diagnostics),
            }
            for cell in run.cells
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "BenchmarkCell",
    "BenchmarkCondition",
    "BenchmarkStatus",
    "DEFAULT_BENCHMARK_CONDITIONS",
    "ExecutionStatus",
    "ReceiptProvenanceError",
    "IsolatedRefinementCell",
    "IsolatedRefinementRun",
    "PairedBenchmarkRun",
    "PairedBenchmarkSummary",
    "corpus_digest_for_loaded",
    "run_isolated_refinement_pair",
    "run_paired_benchmark",
    "rescore_paired_receipts",
    "write_benchmark_diagnostics",
    "write_benchmark_report",
]
