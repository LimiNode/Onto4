"""Sequential, privacy-preserving evaluation receipts for clarification corpora."""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from .clarification_corpus import ClarificationCorpus, ClarificationCorpusCase


class EvaluationOutcome(str, Enum):
    TRANSPORT_ERROR = "transport_error"
    REQUEST_TIMEOUT = "request_timeout"
    CASE_DEADLINE_EXCEEDED = "case_deadline_exceeded"
    EMPTY_CONTENT = "empty_content"
    JSON_INVALID = "json_invalid"
    SCHEMA_INVALID = "schema_invalid"
    PROVENANCE_INVALID = "provenance_invalid"
    FORMALIZATION_UNRESOLVED = "formalization_unresolved"
    ASSESSMENT_COMPLETED = "assessment_completed"
    CLARIFICATION_REQUESTED = "clarification_requested"
    CLARIFICATION_ABSTAINED = "clarification_abstained"
    STRUCTURAL_RESOLUTION = "structural_resolution"
    SEMANTIC_FIDELITY_UNVERIFIED = "semantic_fidelity_unverified"
    UNSUPPORTED_DIALOGUE_STEP = "unsupported_dialogue_step"
    CONTEXT_UNAVAILABLE = "context_unavailable"
    NEED_EVIDENCE = "need_evidence"
    CANNOT_PROCEED = "cannot_proceed"
    DIALOGUE_INCOMPLETE = "dialogue_incomplete"
    QUESTION_INTENT_MISMATCH = "question_intent_mismatch"
    QUESTION_INTENT_UNVERIFIED = "question_intent_unverified"
    SCRIPT_EXHAUSTED = "script_exhausted"


class CaseExecutor(Protocol):
    def __call__(
        self, case: ClarificationCorpusCase, *, request_timeout_seconds: float
    ) -> "CaseExecution":
        ...


@dataclass(frozen=True)
class CaseExecution:
    """Safe result returned by a provider/corpus adapter.

    It deliberately contains no prompt, source text, raw response or credential.
    """

    outcome: EvaluationOutcome
    provider_calls: int = 0
    stage_timings: Mapping[str, float] = field(default_factory=dict)
    stage_outcomes: Mapping[str, str] = field(default_factory=dict)
    stage_details: Mapping[str, str] = field(default_factory=dict)
    semantic_verdict: str | None = None
    detail_code: str | None = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AttemptRecord:
    """Safe accounting for one sequential case attempt."""

    attempt: int
    outcome: EvaluationOutcome
    elapsed_seconds: float
    provider_calls: int = 0
    provider_stage_seconds: Mapping[str, float] = field(default_factory=dict)
    provider_stage_outcomes: Mapping[str, str] = field(default_factory=dict)
    provider_stage_details: Mapping[str, str] = field(default_factory=dict)
    detail_code: str | None = None


@dataclass(frozen=True)
class EvaluationConfig:
    request_timeout_seconds: float = 30.0
    case_deadline_seconds: float = 120.0
    inter_case_delay_seconds: float = 0.0
    max_retries: int = 0
    provider: str = "fixture"
    model: str = "offline-fixture"
    mode: str = "offline"
    prompt_version: str = "unspecified"
    prompt_hash: str | None = None
    commit_sha: str | None = None
    model_artifact_digest: str | None = None
    temperature: float | None = None
    thinking_enabled: bool | None = None
    max_output_tokens: int | None = None
    variant: str = "default"
    prompt_variant: str = "baseline"
    requested_conceptual_depth: str = "auto"
    run_id: str | None = None
    context_profile_digests: Mapping[str, str] = field(default_factory=dict)
    interpretation_context_mode: str = "context_late"
    refinement_mode: str = "full_snapshot"

    def __post_init__(self) -> None:
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive.")
        if self.case_deadline_seconds <= 0:
            raise ValueError("case_deadline_seconds must be positive.")
        if self.inter_case_delay_seconds < 0:
            raise ValueError("inter_case_delay_seconds must not be negative.")
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative.")
        if self.temperature is not None and self.temperature < 0:
            raise ValueError("temperature must not be negative.")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive.")
        if not self.variant.strip():
            raise ValueError("variant must not be empty.")
        if self.requested_conceptual_depth not in {
            "auto",
            "ordinary",
            "reflective",
            "philosophical",
            "ontology_sensitive",
        }:
            raise ValueError("requested_conceptual_depth must be a supported depth or auto.")
        if self.interpretation_context_mode not in {"context_late", "context_aware"}:
            raise ValueError(
                "interpretation_context_mode must be context_late or context_aware."
            )
        if self.refinement_mode not in {"full_snapshot", "typed_delta"}:
            raise ValueError("refinement_mode must be full_snapshot or typed_delta.")


@dataclass(frozen=True)
class CaseReceipt:
    case_id: str
    case_mode: str
    outcome: EvaluationOutcome
    elapsed_seconds: float
    provider_stage_seconds: Mapping[str, float] = field(default_factory=dict)
    provider_stage_outcomes: Mapping[str, str] = field(default_factory=dict)
    provider_stage_details: Mapping[str, str] = field(default_factory=dict)
    provider_calls: int = 0
    attempts: int = 1
    semantic_verdict: str | None = None
    detail_code: str | None = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    attempt_history: tuple[AttemptRecord, ...] = ()
    complete: bool = True
    resume_allowed: bool = False


@dataclass(frozen=True)
class EvaluationSummary:
    total_cases: int
    completed_cases: int
    outcome_counts: Mapping[str, int]
    mode_counts: Mapping[str, Mapping[str, int]]
    timeout_rate: float
    schema_valid_rate: float | None
    median_stage_latency_seconds: float | None
    p95_stage_latency_seconds: float | None
    provider_calls_per_completed_case: float | None
    semantic_scored_cases: int
    verdict_observed_cases: int
    oracle_comparable_cases: int
    oracle_passed_cases: int
    human_review_cases: int
    protocol_coverage: int
    dialogue_supported_cases: int
    dialogue_completed_cases: int


@dataclass(frozen=True)
class EvaluationRun:
    corpus_name: str
    corpus_version: int
    corpus_digest: str
    config: EvaluationConfig
    receipts: tuple[CaseReceipt, ...]
    summary: EvaluationSummary


def corpus_digest(path: str | Path) -> str:
    """Return a stable digest without retaining corpus contents in receipts."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _invoke_with_deadline(
    executor: CaseExecutor,
    case: ClarificationCorpusCase,
    *,
    timeout_seconds: float,
) -> CaseExecution:
    """Invoke one bounded provider call synchronously.

    The executor owns the actual network timeout.  Keeping this call
    synchronous guarantees that a timed-out executor cannot overlap a retry or
    the next corpus case; a non-cooperative executor blocks the run instead of
    leaving a daemon thread issuing requests in the background.
    """

    try:
        result = executor(case, request_timeout_seconds=timeout_seconds)
    except Exception as exc:  # provider failures become typed transport outcomes
        return CaseExecution(
            EvaluationOutcome.TRANSPORT_ERROR,
            detail_code=type(exc).__name__,
        )
    if result is None:
        return CaseExecution(EvaluationOutcome.EMPTY_CONTENT)
    return result


def _retryable(outcome: EvaluationOutcome) -> bool:
    return outcome in {
        EvaluationOutcome.TRANSPORT_ERROR,
        EvaluationOutcome.REQUEST_TIMEOUT,
        EvaluationOutcome.CASE_DEADLINE_EXCEEDED,
    }


def _stage_latencies(receipts: Iterable[CaseReceipt]) -> list[float]:
    return [
        elapsed
        for receipt in receipts
        for elapsed in receipt.provider_stage_seconds.values()
        if elapsed >= 0
    ]


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _summary(receipts: tuple[CaseReceipt, ...]) -> EvaluationSummary:
    counts: dict[str, int] = {}
    mode_counts: dict[str, dict[str, int]] = {}
    for receipt in receipts:
        counts[receipt.outcome.value] = counts.get(receipt.outcome.value, 0) + 1
        bucket = mode_counts.setdefault(receipt.case_mode, {})
        bucket[receipt.outcome.value] = bucket.get(receipt.outcome.value, 0) + 1
    completed = sum(
        1
        for receipt in receipts
        if receipt.outcome
        not in {
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
            EvaluationOutcome.SCRIPT_EXHAUSTED,
        }
    )
    stage_latencies = _stage_latencies(receipts)
    provider_calls = sum(receipt.provider_calls for receipt in receipts if receipt.complete)
    schema_observations = [
        receipt
        for receipt in receipts
        if receipt.provider_calls > 0
        if receipt.outcome
        not in {
            EvaluationOutcome.TRANSPORT_ERROR,
            EvaluationOutcome.REQUEST_TIMEOUT,
            EvaluationOutcome.CASE_DEADLINE_EXCEEDED,
            EvaluationOutcome.EMPTY_CONTENT,
        }
    ]
    verdict_observed = sum(
        receipt.semantic_verdict is not None
        and receipt.outcome is EvaluationOutcome.ASSESSMENT_COMPLETED
        for receipt in receipts
    )
    dialogue_supported_outcomes = {
        EvaluationOutcome.FORMALIZATION_UNRESOLVED,
        EvaluationOutcome.ASSESSMENT_COMPLETED,
        EvaluationOutcome.CLARIFICATION_REQUESTED,
        EvaluationOutcome.CLARIFICATION_ABSTAINED,
        EvaluationOutcome.STRUCTURAL_RESOLUTION,
        EvaluationOutcome.DIALOGUE_INCOMPLETE,
        EvaluationOutcome.QUESTION_INTENT_MISMATCH,
        EvaluationOutcome.QUESTION_INTENT_UNVERIFIED,
        EvaluationOutcome.SCRIPT_EXHAUSTED,
    }
    dialogue_completed_outcomes = {
        EvaluationOutcome.ASSESSMENT_COMPLETED,
        EvaluationOutcome.CLARIFICATION_ABSTAINED,
    }
    dialogue_supported = sum(
        receipt.case_mode == "dialogue"
        and receipt.outcome in dialogue_supported_outcomes
        for receipt in receipts
    )
    dialogue_completed = sum(
        receipt.case_mode == "dialogue"
        and receipt.outcome in dialogue_completed_outcomes
        for receipt in receipts
    )
    return EvaluationSummary(
        total_cases=len(receipts),
        completed_cases=completed,
        outcome_counts=counts,
        mode_counts=mode_counts,
        timeout_rate=(
            sum(
                receipt.outcome
                in {
                    EvaluationOutcome.REQUEST_TIMEOUT,
                    EvaluationOutcome.CASE_DEADLINE_EXCEEDED,
                }
                for receipt in receipts
            )
            / len(receipts)
            if receipts
            else 0.0
        ),
        schema_valid_rate=(
            sum(
                receipt.outcome
                not in {
                    EvaluationOutcome.JSON_INVALID,
                    EvaluationOutcome.SCHEMA_INVALID,
                }
                for receipt in schema_observations
            )
            / len(schema_observations)
            if schema_observations
            else None
        ),
        median_stage_latency_seconds=(
            statistics.median(stage_latencies) if stage_latencies else None
        ),
        p95_stage_latency_seconds=_percentile(stage_latencies, 0.95),
        provider_calls_per_completed_case=(
            provider_calls / completed if completed else None
        ),
        # No hidden-oracle scorer is part of this runner yet.  An observed
        # verdict is reported separately and must not be presented as a
        # verified semantic score.
        semantic_scored_cases=0,
        verdict_observed_cases=verdict_observed,
        oracle_comparable_cases=0,
        oracle_passed_cases=0,
        human_review_cases=sum(
            receipt.outcome is EvaluationOutcome.QUESTION_INTENT_UNVERIFIED
            for receipt in receipts
        ),
        protocol_coverage=len(receipts),
        dialogue_supported_cases=dialogue_supported,
        dialogue_completed_cases=dialogue_completed,
    )


def _receipt_json(receipt: CaseReceipt) -> dict[str, Any]:
    value = asdict(receipt)
    value["outcome"] = receipt.outcome.value
    return value


def _manifest(corpus: ClarificationCorpus, digest: str, config: EvaluationConfig) -> dict[str, Any]:
    return {
        "manifest_schema_version": 2,
        "record_type": "manifest",
        "corpus_name": corpus.name,
        "corpus_version": corpus.version,
        "corpus_digest": digest,
        "config": asdict(config),
    }


def _write_receipts(
    path: Path,
    manifest: Mapping[str, Any],
    receipts: Iterable[CaseReceipt],
) -> None:
    """Atomically rewrite the manifest and latest receipt for each case."""

    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(manifest), sort_keys=True) + "\n")
        for receipt in receipts:
            handle.write(json.dumps(_receipt_json(receipt), sort_keys=True) + "\n")
    temporary.replace(path)


def _load_existing_receipts(
    path: Path,
    *,
    expected_manifest: Mapping[str, Any],
) -> dict[str, CaseReceipt]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("Receipt file is empty and has no manifest.")
    try:
        manifest = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise ValueError("Receipt manifest is not valid JSON.") from exc
    if not isinstance(manifest, Mapping):
        raise ValueError("Receipt manifest must be a JSON object.")
    expected = dict(expected_manifest)
    if manifest != expected:
        legacy_manifest = dict(manifest)
        if (
            "manifest_schema_version" not in legacy_manifest
            and expected.get("manifest_schema_version") == 2
        ):
            # Receipts written before schema versioning remain resumable when
            # every other provenance field still matches this run.  The
            # benchmark re-scorer deliberately does not use this migration.
            legacy_manifest["manifest_schema_version"] = expected["manifest_schema_version"]
        legacy_config = legacy_manifest.get("config")
        expected_config = expected.get("config")
        if isinstance(legacy_config, dict) and isinstance(expected_config, dict):
            migrated_config = dict(legacy_config)
            legacy_defaults = {
                "interpretation_context_mode": "context_late",
                "refinement_mode": "full_snapshot",
            }
            for name, default in legacy_defaults.items():
                if name not in migrated_config and expected_config.get(name) == default:
                    migrated_config[name] = default
            legacy_manifest["config"] = migrated_config
        if legacy_manifest != expected:
            raise ValueError("Receipt manifest does not match this evaluation run.")
    existing: dict[str, CaseReceipt] = {}
    for index, line in enumerate(lines[1:], start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) - 1:
                # A process may have been interrupted during the final write;
                # discard only that uncommitted tail and recover safely.
                break
            raise ValueError("Receipt file contains invalid JSON before its tail.") from exc
        if item.get("record_type") == "manifest":
            raise ValueError("Receipt file contains a second manifest record.")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("Receipt record has no valid case_id.")
        receipt = CaseReceipt(
            case_id=case_id,
            case_mode=item.get("case_mode", "single_pass"),
            outcome=EvaluationOutcome(item["outcome"]),
            elapsed_seconds=float(item["elapsed_seconds"]),
            provider_stage_seconds=item.get("provider_stage_seconds", {}),
            provider_stage_outcomes=item.get("provider_stage_outcomes", {}),
            provider_stage_details=item.get("provider_stage_details", {}),
            provider_calls=int(item.get("provider_calls", 0)),
            attempts=int(item.get("attempts", 1)),
            semantic_verdict=item.get("semantic_verdict"),
            detail_code=item.get("detail_code"),
            diagnostics=item.get("diagnostics", {}),
            attempt_history=tuple(
                AttemptRecord(
                    attempt=int(raw_attempt.get("attempt", index)),
                    outcome=EvaluationOutcome(raw_attempt["outcome"]),
                    elapsed_seconds=float(raw_attempt.get("elapsed_seconds", 0.0)),
                    provider_calls=int(raw_attempt.get("provider_calls", 0)),
                    provider_stage_seconds=raw_attempt.get("provider_stage_seconds", {}),
                    provider_stage_outcomes=raw_attempt.get("provider_stage_outcomes", {}),
                    provider_stage_details=raw_attempt.get("provider_stage_details", {}),
                    detail_code=raw_attempt.get("detail_code"),
                )
                for index, raw_attempt in enumerate(item.get("attempt_history", ()), start=1)
                if isinstance(raw_attempt, Mapping)
            ),
            complete=bool(item.get("complete", True)),
            resume_allowed=bool(item.get("resume_allowed", False)),
        )
        if case_id in existing and existing[case_id] != receipt:
            raise ValueError(f"Conflicting duplicate receipt for case {case_id!r}.")
        existing[case_id] = receipt
    return existing


class SequentialEvaluationRunner:
    """Run one corpus worker sequentially and persist each receipt immediately."""

    def __init__(
        self,
        executor: CaseExecutor,
        *,
        config: EvaluationConfig,
        receipt_path: str | Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.executor = executor
        self.config = config
        self.receipt_path = Path(receipt_path) if receipt_path is not None else None
        self.sleep = sleep
        self.clock = clock

    def run(self, corpus: ClarificationCorpus, *, digest: str) -> EvaluationRun:
        manifest = _manifest(corpus, digest, self.config)
        existing: dict[str, CaseReceipt] = {}
        if self.receipt_path is not None and self.receipt_path.exists():
            existing = _load_existing_receipts(
                self.receipt_path,
                expected_manifest=manifest,
            )
            _write_receipts(self.receipt_path, manifest, existing.values())

        receipts: list[CaseReceipt] = []
        for case in corpus.cases:
            if (
                case.case_id in existing
                and existing[case.case_id].complete
                and not existing[case.case_id].resume_allowed
            ):
                receipts.append(existing[case.case_id])
                continue
            started = self.clock()
            execution: CaseExecution | None = None
            attempts = 0
            attempt_history: list[AttemptRecord] = []
            while attempts <= self.config.max_retries:
                attempts += 1
                attempt_started = self.clock()
                remaining = self.config.case_deadline_seconds - (
                    self.clock() - started
                )
                if remaining <= 0:
                    execution = CaseExecution(
                        EvaluationOutcome.CASE_DEADLINE_EXCEEDED,
                        detail_code="case_deadline",
                    )
                else:
                    execution = _invoke_with_deadline(
                        self.executor,
                        case,
                        timeout_seconds=min(
                            self.config.request_timeout_seconds,
                            remaining,
                        ),
                    )
                    if (
                        self.clock() - started >= self.config.case_deadline_seconds
                    ):
                        execution = CaseExecution(
                            EvaluationOutcome.CASE_DEADLINE_EXCEEDED,
                            provider_calls=execution.provider_calls,
                            stage_timings=execution.stage_timings,
                            stage_outcomes=execution.stage_outcomes,
                            stage_details=execution.stage_details,
                            detail_code="case_deadline",
                            diagnostics=execution.diagnostics,
                        )
                attempt_history.append(
                    AttemptRecord(
                        attempt=attempts,
                        outcome=execution.outcome,
                        elapsed_seconds=max(0.0, self.clock() - attempt_started),
                        provider_calls=execution.provider_calls,
                        provider_stage_seconds=dict(execution.stage_timings),
                        provider_stage_outcomes=dict(execution.stage_outcomes),
                        provider_stage_details=dict(execution.stage_details),
                        detail_code=execution.detail_code,
                    )
                )
                if remaining <= 0:
                    break
                if not _retryable(execution.outcome) or attempts > self.config.max_retries:
                    break
            assert execution is not None
            if len(attempt_history) == 1:
                receipt_stage_seconds = dict(execution.stage_timings)
                receipt_stage_outcomes = dict(execution.stage_outcomes)
                receipt_stage_details = dict(execution.stage_details)
                receipt_provider_calls = execution.provider_calls
            else:
                receipt_stage_seconds = {
                    f"attempt#{record.attempt}:{stage}": elapsed
                    for record in attempt_history
                    for stage, elapsed in record.provider_stage_seconds.items()
                }
                receipt_stage_outcomes = {
                    f"attempt#{record.attempt}:{stage}": outcome
                    for record in attempt_history
                    for stage, outcome in record.provider_stage_outcomes.items()
                }
                receipt_stage_details = {
                    f"attempt#{record.attempt}:{stage}": detail
                    for record in attempt_history
                    for stage, detail in record.provider_stage_details.items()
                }
                receipt_provider_calls = sum(
                    record.provider_calls for record in attempt_history
                )
            receipt = CaseReceipt(
                case_id=case.case_id,
                case_mode=getattr(case, "mode", "single_pass"),
                outcome=execution.outcome,
                elapsed_seconds=max(0.0, self.clock() - started),
                provider_stage_seconds=receipt_stage_seconds,
                provider_stage_outcomes=receipt_stage_outcomes,
                provider_stage_details=receipt_stage_details,
                provider_calls=receipt_provider_calls,
                attempts=attempts,
                semantic_verdict=execution.semantic_verdict,
                detail_code=execution.detail_code,
                diagnostics=dict(execution.diagnostics),
                attempt_history=tuple(attempt_history),
                complete=True,
                resume_allowed=execution.outcome in {
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
                    EvaluationOutcome.SCRIPT_EXHAUSTED,
                },
            )
            receipts.append(receipt)
            existing[case.case_id] = receipt
            if self.receipt_path is not None:
                self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
                _write_receipts(self.receipt_path, manifest, existing.values())
            if case is not corpus.cases[-1] and self.config.inter_case_delay_seconds:
                self.sleep(self.config.inter_case_delay_seconds)

        return EvaluationRun(
            corpus_name=corpus.name,
            corpus_version=corpus.version,
            corpus_digest=digest,
            config=self.config,
            receipts=tuple(receipts),
            summary=_summary(tuple(receipts)),
        )


def offline_fixture_executor(
    case: ClarificationCorpusCase, *, request_timeout_seconds: float
) -> CaseExecution:
    """Record protocol coverage without pretending to run hidden semantics."""

    del request_timeout_seconds
    if getattr(case, "mode", "single_pass") == "dialogue":
        return CaseExecution(
            EvaluationOutcome.UNSUPPORTED_DIALOGUE_STEP,
            detail_code="fixture_protocol_only",
        )
    return CaseExecution(
        EvaluationOutcome.SEMANTIC_FIDELITY_UNVERIFIED,
        detail_code="offline_fixture_has_no_model_evidence",
    )


def write_markdown_report(run: EvaluationRun, path: str | Path) -> None:
    target = Path(path)
    lines = [
        f"# Evaluation run: {run.corpus_name}",
        "",
        f"- Corpus version: `{run.corpus_version}`",
        f"- Corpus digest: `{run.corpus_digest}`",
        f"- Mode: `{run.config.mode}`",
        f"- Provider/model: `{run.config.provider}` / `{run.config.model}`",
        f"- Model artifact digest: `{run.config.model_artifact_digest or 'unspecified'}`",
        f"- Prompt version: `{run.config.prompt_version}`",
        f"- Prompt variant: `{run.config.prompt_variant}`",
        f"- Requested conceptual depth: `{run.config.requested_conceptual_depth}`",
        f"- Prompt hash: `{run.config.prompt_hash or 'unspecified'}`",
        f"- Commit: `{run.config.commit_sha or 'unspecified'}`",
        f"- Variant: `{run.config.variant}`",
        f"- Run ID: `{run.config.run_id or 'unspecified'}`",
        f"- Request timeout: `{run.config.request_timeout_seconds}s`",
        f"- Case deadline: `{run.config.case_deadline_seconds}s`",
        "",
        "## Summary",
        "",
        f"- Cases: `{run.summary.total_cases}`",
        f"- Completed protocol outcomes: `{run.summary.completed_cases}`",
        f"- Protocol coverage: `{run.summary.protocol_coverage}/{run.summary.total_cases}`",
        f"- Semantic scored cases: `{run.summary.semantic_scored_cases}`",
        f"- Verdicts observed (not oracle-scored): `{run.summary.verdict_observed_cases}`",
        f"- Oracle-comparable cases: `{run.summary.oracle_comparable_cases}`",
        f"- Oracle-passed cases: `{run.summary.oracle_passed_cases}`",
        f"- Human-review cases: `{run.summary.human_review_cases}`",
        f"- Dialogue supported cases: `{run.summary.dialogue_supported_cases}`",
        f"- Dialogue completed cases: `{run.summary.dialogue_completed_cases}`",
        f"- Timeout rate: `{run.summary.timeout_rate:.3f}`",
        f"- Schema-valid rate: `{run.summary.schema_valid_rate if run.summary.schema_valid_rate is not None else 'n/a'}`",
        f"- Median stage latency: `{run.summary.median_stage_latency_seconds}`",
        f"- P95 stage latency: `{run.summary.p95_stage_latency_seconds}`",
        "",
        "| Outcome | Count |",
        "|---|---:|",
    ]
    lines.extend(
        f"| `{outcome}` | {count} |"
        for outcome, count in sorted(run.summary.outcome_counts.items())
    )
    lines.extend(["", "## Outcomes by case mode", "", "| Mode | Outcome | Count |", "|---|---|---:|"])
    for mode, outcomes in sorted(run.summary.mode_counts.items()):
        lines.extend(
            f"| `{mode}` | `{outcome}` | {count} |"
            for outcome, count in sorted(outcomes.items())
        )
    lines.extend(
        [
            "",
            "Semantic fidelity is not inferred from transport, schema or fixture "
            "coverage. Hidden oracle fields and raw model payloads are excluded "
            "from this report.",
        ]
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


__all__ = [
    "CaseExecution",
    "CaseReceipt",
    "EvaluationConfig",
    "EvaluationOutcome",
    "EvaluationRun",
    "EvaluationSummary",
    "SequentialEvaluationRunner",
    "corpus_digest",
    "offline_fixture_executor",
    "write_markdown_report",
]
