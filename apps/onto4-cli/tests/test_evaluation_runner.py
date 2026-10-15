import json
import time

import pytest

from onto4.pipeline import (
    CaseExecution,
    EvaluationConfig,
    EvaluationOutcome,
    SequentialEvaluationRunner,
    corpus_digest,
    load_clarification_corpus,
    offline_fixture_executor,
    write_markdown_report,
)


ROOT = __import__("pathlib").Path(__file__).parents[1]
CORPUS = ROOT / "eval/clarification/epistemic-ontology-v1.yaml"


def test_offline_runner_covers_entire_corpus_without_oracle_or_payload(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    receipt_path = tmp_path / "receipts.jsonl"
    report_path = tmp_path / "report.md"
    run = SequentialEvaluationRunner(
        offline_fixture_executor,
        config=EvaluationConfig(),
        receipt_path=receipt_path,
    ).run(corpus, digest=corpus_digest(CORPUS))
    write_markdown_report(run, report_path)

    assert run.summary.total_cases == 27
    assert len(run.receipts) == 27
    assert any(
        receipt.outcome is EvaluationOutcome.UNSUPPORTED_DIALOGUE_STEP
        for receipt in run.receipts
    )
    assert all(receipt.semantic_verdict is None for receipt in run.receipts)
    assert run.summary.schema_valid_rate is None
    assert run.summary.semantic_scored_cases == 0
    assert run.summary.protocol_coverage == 27
    raw = receipt_path.read_text(encoding="utf-8")
    assert "expected_after_answer" not in raw
    assert "utterance" not in raw
    assert "raw" not in raw.lower()
    assert "Semantic fidelity is not inferred" in report_path.read_text(encoding="utf-8")


def test_runner_is_sequential_and_persists_each_case(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    active = 0
    max_active = 0

    def executor(case, *, request_timeout_seconds):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.001)
        active -= 1
        return CaseExecution(
            EvaluationOutcome.ASSESSMENT_COMPLETED,
            provider_calls=1,
            stage_timings={"interpretation": 0.001},
        )

    receipt_path = tmp_path / "receipts.jsonl"
    run = SequentialEvaluationRunner(
        executor,
        config=EvaluationConfig(),
        receipt_path=receipt_path,
    ).run(corpus, digest="digest")

    assert max_active == 1
    assert run.summary.total_cases == 27
    assert len(receipt_path.read_text(encoding="utf-8").splitlines()) == 28


def test_timeout_result_finishes_before_retry_or_next_case():
    corpus = load_clarification_corpus(CORPUS)
    active = 0
    max_active = 0
    calls = 0

    def executor(case, *, request_timeout_seconds):
        nonlocal active, max_active, calls
        calls += 1
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.002)
        active -= 1
        return CaseExecution(
            EvaluationOutcome.REQUEST_TIMEOUT
            if calls == 1
            else EvaluationOutcome.ASSESSMENT_COMPLETED
        )

    run = SequentialEvaluationRunner(
        executor,
        config=EvaluationConfig(max_retries=1),
    ).run(corpus, digest="digest")

    assert max_active == 1
    assert run.receipts[0].attempts == 2


def test_runner_resumes_completed_receipts_without_reexecuting(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    receipt_path = tmp_path / "receipts.jsonl"
    calls = []

    def executor(case, *, request_timeout_seconds):
        calls.append(case.case_id)
        return CaseExecution(EvaluationOutcome.ASSESSMENT_COMPLETED)

    config = EvaluationConfig()
    SequentialEvaluationRunner(executor, config=config, receipt_path=receipt_path).run(
        corpus, digest="digest"
    )
    first_call_count = len(calls)
    SequentialEvaluationRunner(executor, config=config, receipt_path=receipt_path).run(
        corpus, digest="digest"
    )

    assert first_call_count == 27
    assert len(calls) == first_call_count


def test_runner_classifies_timeout_and_retries_only_transport_classes(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    calls = 0

    def executor(case, *, request_timeout_seconds):
        nonlocal calls
        calls += 1
        if calls == 1:
            return CaseExecution(EvaluationOutcome.REQUEST_TIMEOUT)
        return CaseExecution(EvaluationOutcome.SCHEMA_INVALID)

    run = SequentialEvaluationRunner(
        executor,
        config=EvaluationConfig(
            request_timeout_seconds=0.001,
            case_deadline_seconds=1.0,
            max_retries=1,
        ),
    ).run(corpus, digest="digest")

    assert run.receipts[0].outcome is EvaluationOutcome.SCHEMA_INVALID
    assert run.receipts[0].attempts == 2


def test_runner_rejects_manifest_mismatch_before_resume(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    path = tmp_path / "receipts.jsonl"
    config = EvaluationConfig(model="model-a")
    SequentialEvaluationRunner(
        offline_fixture_executor,
        config=config,
        receipt_path=path,
    ).run(corpus, digest="digest")

    with pytest.raises(ValueError, match="manifest"):
        SequentialEvaluationRunner(
            offline_fixture_executor,
            config=EvaluationConfig(model="model-b"),
            receipt_path=path,
        ).run(corpus, digest="digest")


def test_runner_retries_technical_receipt_but_skips_completed_cases(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    path = tmp_path / "receipts.jsonl"
    first_run = True
    calls = []

    def executor(case, *, request_timeout_seconds):
        nonlocal first_run
        calls.append(case.case_id)
        if first_run and case.case_id == corpus.cases[0].case_id:
            return CaseExecution(EvaluationOutcome.SCHEMA_INVALID)
        return CaseExecution(EvaluationOutcome.ASSESSMENT_COMPLETED)

    config = EvaluationConfig()
    SequentialEvaluationRunner(executor, config=config, receipt_path=path).run(
        corpus, digest="digest"
    )
    first_run = False
    calls_before_resume = len(calls)
    resumed = SequentialEvaluationRunner(executor, config=config, receipt_path=path).run(
        corpus, digest="digest"
    )

    assert len(calls) == calls_before_resume + 1
    assert resumed.receipts[0].outcome is EvaluationOutcome.ASSESSMENT_COMPLETED


def test_runner_recovers_truncated_tail_without_accepting_it(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    path = tmp_path / "receipts.jsonl"
    config = EvaluationConfig()
    SequentialEvaluationRunner(
        offline_fixture_executor,
        config=config,
        receipt_path=path,
    ).run(corpus, digest="digest")
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"case_id":"truncated"')

    run = SequentialEvaluationRunner(
        offline_fixture_executor,
        config=config,
        receipt_path=path,
    ).run(corpus, digest="digest")

    assert len(run.receipts) == 27
    assert "truncated" not in path.read_text(encoding="utf-8")


def test_receipt_json_is_machine_readable(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    path = tmp_path / "receipts.jsonl"
    SequentialEvaluationRunner(
        offline_fixture_executor,
        config=EvaluationConfig(),
        receipt_path=path,
    ).run(corpus, digest="digest")

    first = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
    assert set(first) >= {"case_id", "case_mode", "outcome", "elapsed_seconds"}
    assert first["outcome"] in {item.value for item in EvaluationOutcome}
