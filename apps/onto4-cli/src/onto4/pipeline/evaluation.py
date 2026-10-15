"""Sequential, privacy-preserving evaluation receipts for clarification corpora."""

from __future__ import annotations

import hashlib
import json
import statistics
import threading
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
    semantic_verdict: str | None = None
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
    commit_sha: str | None = None

    def __post_init__(self) -> None:
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive.")
        if self.case_deadline_seconds <= 0:
            raise ValueError("case_deadline_seconds must be positive.")
        if self.inter_case_delay_seconds < 0:
            raise ValueError("inter_case_delay_seconds must not be negative.")
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative.")


@dataclass(frozen=True)
class CaseReceipt:
    case_id: str
    case_mode: str
    outcome: EvaluationOutcome
    elapsed_seconds: float
    provider_stage_seconds: Mapping[str, float] = field(default_factory=dict)
    provider_calls: int = 0
    attempts: int = 1
    semantic_verdict: str | None = None
    detail_code: str | None = None
    complete: bool = True


@dataclass(frozen=True)
class EvaluationSummary:
    total_cases: int
    completed_cases: int
    outcome_counts: Mapping[str, int]
    mode_counts: Mapping[str, Mapping[str, int]]
    timeout_rate: float
    schema_valid_rate: float
    median_stage_latency_seconds: float | None
    p95_stage_latency_seconds: float | None
    provider_calls_per_completed_case: float | None


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
    result: list[CaseExecution] = []
    error: list[BaseException] = []

    def target() -> None:
        try:
            result.append(
                executor(case, request_timeout_seconds=timeout_seconds)
            )
        except BaseException as exc:  # converted to a typed transport outcome
            error.append(exc)

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        return CaseExecution(EvaluationOutcome.REQUEST_TIMEOUT, detail_code="deadline")
    if error:
        return CaseExecution(
            EvaluationOutcome.TRANSPORT_ERROR,
            detail_code=type(error[0]).__name__,
        )
    if not result:
        return CaseExecution(EvaluationOutcome.EMPTY_CONTENT)
    return result[0]


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
        }
    )
    stage_latencies = _stage_latencies(receipts)
    provider_calls = sum(receipt.provider_calls for receipt in receipts if receipt.complete)
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
                for receipt in receipts
            )
            / len(receipts)
            if receipts
            else 0.0
        ),
        median_stage_latency_seconds=(
            statistics.median(stage_latencies) if stage_latencies else None
        ),
        p95_stage_latency_seconds=_percentile(stage_latencies, 0.95),
        provider_calls_per_completed_case=(
            provider_calls / completed if completed else None
        ),
    )


def _receipt_json(receipt: CaseReceipt) -> dict[str, Any]:
    value = asdict(receipt)
    value["outcome"] = receipt.outcome.value
    return value


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
        existing: dict[str, CaseReceipt] = {}
        if self.receipt_path is not None and self.receipt_path.exists():
            for line in self.receipt_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if item.get("record_type") == "manifest":
                    continue
                existing[item["case_id"]] = CaseReceipt(
                    case_id=item["case_id"],
                    case_mode=item.get("case_mode", "single_pass"),
                    outcome=EvaluationOutcome(item["outcome"]),
                    elapsed_seconds=float(item["elapsed_seconds"]),
                    provider_stage_seconds=item.get("provider_stage_seconds", {}),
                    provider_calls=int(item.get("provider_calls", 0)),
                    attempts=int(item.get("attempts", 1)),
                    semantic_verdict=item.get("semantic_verdict"),
                    detail_code=item.get("detail_code"),
                    complete=bool(item.get("complete", True)),
                )

        receipts: list[CaseReceipt] = []
        for case in corpus.cases:
            if case.case_id in existing and existing[case.case_id].complete:
                receipts.append(existing[case.case_id])
                continue
            started = self.clock()
            execution: CaseExecution | None = None
            attempts = 0
            while attempts <= self.config.max_retries:
                attempts += 1
                remaining = self.config.case_deadline_seconds - (
                    self.clock() - started
                )
                if remaining <= 0:
                    execution = CaseExecution(
                        EvaluationOutcome.CASE_DEADLINE_EXCEEDED,
                        detail_code="case_deadline",
                    )
                    break
                execution = _invoke_with_deadline(
                    self.executor,
                    case,
                    timeout_seconds=min(
                        self.config.request_timeout_seconds,
                        remaining,
                    ),
                )
                if (
                    execution.outcome is EvaluationOutcome.REQUEST_TIMEOUT
                    and self.clock() - started >= self.config.case_deadline_seconds
                ):
                    execution = CaseExecution(
                        EvaluationOutcome.CASE_DEADLINE_EXCEEDED,
                        provider_calls=execution.provider_calls,
                        stage_timings=execution.stage_timings,
                        detail_code="case_deadline",
                    )
                if not _retryable(execution.outcome) or attempts > self.config.max_retries:
                    break
            assert execution is not None
            receipt = CaseReceipt(
                case_id=case.case_id,
                case_mode=getattr(case, "mode", "single_pass"),
                outcome=execution.outcome,
                elapsed_seconds=max(0.0, self.clock() - started),
                provider_stage_seconds=dict(execution.stage_timings),
                provider_calls=execution.provider_calls,
                attempts=attempts,
                semantic_verdict=execution.semantic_verdict,
                detail_code=execution.detail_code,
                complete=True,
            )
            receipts.append(receipt)
            if self.receipt_path is not None:
                self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
                if not self.receipt_path.exists() or self.receipt_path.stat().st_size == 0:
                    manifest = {
                        "record_type": "manifest",
                        "corpus_name": corpus.name,
                        "corpus_version": corpus.version,
                        "corpus_digest": digest,
                        "config": asdict(self.config),
                    }
                    self.receipt_path.write_text(
                        json.dumps(manifest, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                with self.receipt_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(_receipt_json(receipt), sort_keys=True) + "\n")
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
        f"- Prompt version: `{run.config.prompt_version}`",
        f"- Commit: `{run.config.commit_sha or 'unspecified'}`",
        f"- Request timeout: `{run.config.request_timeout_seconds}s`",
        f"- Case deadline: `{run.config.case_deadline_seconds}s`",
        "",
        "## Summary",
        "",
        f"- Cases: `{run.summary.total_cases}`",
        f"- Completed protocol outcomes: `{run.summary.completed_cases}`",
        f"- Timeout rate: `{run.summary.timeout_rate:.3f}`",
        f"- Schema-valid rate: `{run.summary.schema_valid_rate:.3f}`",
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
