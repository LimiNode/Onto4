import json
import time
from dataclasses import replace

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
    assert run.summary.dialogue_supported_cases == 0
    assert run.summary.dialogue_completed_cases == 0
    raw = receipt_path.read_text(encoding="utf-8")
    assert "expected_after_answer" not in raw
    assert "utterance" not in raw
    assert "raw" not in raw.lower()
    report = report_path.read_text(encoding="utf-8")
    assert "Dialogue supported cases: `0`" in report
    assert "Dialogue completed cases: `0`" in report
    assert "Semantic fidelity is not inferred" in report


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


def test_retry_receipt_preserves_attempt_level_accounting():
    corpus = load_clarification_corpus(CORPUS)
    calls = 0

    def executor(case, *, request_timeout_seconds):
        nonlocal calls
        calls += 1
        if calls == 1:
            return CaseExecution(
                EvaluationOutcome.REQUEST_TIMEOUT,
                provider_calls=2,
                stage_timings={"interpretation": 0.1},
                stage_outcomes={"interpretation": "failed"},
                stage_details={"interpretation": "transport"},
                detail_code="first",
            )
        return CaseExecution(
            EvaluationOutcome.ASSESSMENT_COMPLETED,
            provider_calls=3,
            stage_timings={"interpretation": 0.2},
            stage_outcomes={"interpretation": "completed"},
            stage_details={"interpretation": "schema_valid"},
            detail_code="second",
        )

    run = SequentialEvaluationRunner(
        executor,
        config=EvaluationConfig(max_retries=1),
    ).run(replace(corpus, cases=(corpus.cases[0],)), digest="digest")

    receipt = run.receipts[0]
    assert receipt.attempts == 2
    assert receipt.provider_calls == 5
    assert [item.outcome for item in receipt.attempt_history] == [
        EvaluationOutcome.REQUEST_TIMEOUT,
        EvaluationOutcome.ASSESSMENT_COMPLETED,
    ]
    assert receipt.provider_stage_seconds == {
        "attempt#1:interpretation": 0.1,
        "attempt#2:interpretation": 0.2,
    }


@pytest.mark.parametrize("signal", (KeyboardInterrupt, SystemExit))
def test_process_control_signals_escape_executor_boundary(signal):
    corpus = load_clarification_corpus(CORPUS)
    calls = []

    def executor(case, *, request_timeout_seconds):
        calls.append(case.case_id)
        raise signal()

    with pytest.raises(signal):
        SequentialEvaluationRunner(
            executor,
            config=EvaluationConfig(max_retries=1),
        ).run(corpus, digest="digest")

    assert len(calls) == 1


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


def test_runner_reads_legacy_receipts_without_attempt_history(tmp_path):
    corpus = replace(
        load_clarification_corpus(CORPUS),
        cases=(load_clarification_corpus(CORPUS).cases[0],),
    )
    receipt_path = tmp_path / "receipts.jsonl"
    calls = []

    def executor(case, *, request_timeout_seconds):
        calls.append(case.case_id)
        return CaseExecution(EvaluationOutcome.ASSESSMENT_COMPLETED)

    config = EvaluationConfig()
    runner = SequentialEvaluationRunner(
        executor, config=config, receipt_path=receipt_path
    )
    first = runner.run(corpus, digest="digest")
    assert first.receipts[0].attempt_history

    lines = receipt_path.read_text(encoding="utf-8").splitlines()
    legacy_receipt = json.loads(lines[1])
    legacy_receipt.pop("attempt_history", None)
    receipt_path.write_text(
        "\n".join([lines[0], json.dumps(legacy_receipt, sort_keys=True)]) + "\n",
        encoding="utf-8",
    )

    resumed = runner.run(corpus, digest="digest")

    assert calls == [corpus.cases[0].case_id]
    assert resumed.receipts[0].attempt_history == ()
    assert resumed.receipts[0].outcome is EvaluationOutcome.ASSESSMENT_COMPLETED


def test_runner_reads_pre_context_mode_manifest_as_context_late(tmp_path):
    corpus = replace(
        load_clarification_corpus(CORPUS),
        cases=(load_clarification_corpus(CORPUS).cases[0],),
    )
    receipt_path = tmp_path / "receipts.jsonl"
    calls = []

    def executor(case, *, request_timeout_seconds):
        calls.append(case.case_id)
        return CaseExecution(EvaluationOutcome.ASSESSMENT_COMPLETED)

    config = EvaluationConfig()
    runner = SequentialEvaluationRunner(
        executor, config=config, receipt_path=receipt_path
    )
    runner.run(corpus, digest="digest")

    lines = receipt_path.read_text(encoding="utf-8").splitlines()
    manifest = json.loads(lines[0])
    manifest["config"].pop("interpretation_context_mode")
    manifest["config"].pop("refinement_mode")
    legacy_receipt = json.loads(lines[1])
    legacy_receipt.pop("attempt_history", None)
    receipt_path.write_text(
        "\n".join(
            [
                json.dumps(manifest, sort_keys=True),
                json.dumps(legacy_receipt, sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resumed = runner.run(corpus, digest="digest")

    assert calls == [corpus.cases[0].case_id]
    assert resumed.receipts[0].outcome is EvaluationOutcome.ASSESSMENT_COMPLETED


def test_runner_resumes_manifest_without_schema_version(tmp_path):
    corpus = replace(
        load_clarification_corpus(CORPUS),
        cases=(load_clarification_corpus(CORPUS).cases[0],),
    )
    receipt_path = tmp_path / "receipts.jsonl"
    calls = []

    def executor(case, *, request_timeout_seconds):
        calls.append(case.case_id)
        return CaseExecution(EvaluationOutcome.ASSESSMENT_COMPLETED)

    runner = SequentialEvaluationRunner(
        executor, config=EvaluationConfig(), receipt_path=receipt_path
    )
    runner.run(corpus, digest="digest")
    lines = receipt_path.read_text(encoding="utf-8").splitlines()
    manifest = json.loads(lines[0])
    manifest.pop("manifest_schema_version")
    receipt_path.write_text(
        "\n".join([json.dumps(manifest, sort_keys=True), lines[1]]) + "\n",
        encoding="utf-8",
    )

    resumed = runner.run(corpus, digest="digest")

    assert calls == [corpus.cases[0].case_id]
    assert resumed.receipts[0].outcome is EvaluationOutcome.ASSESSMENT_COMPLETED


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


def test_runner_marks_late_success_as_case_deadline_exceeded():
    corpus = load_clarification_corpus(CORPUS)

    def executor(case, *, request_timeout_seconds):
        time.sleep(0.01)
        return CaseExecution(EvaluationOutcome.ASSESSMENT_COMPLETED)

    run = SequentialEvaluationRunner(
        executor,
        config=EvaluationConfig(case_deadline_seconds=0.001),
    ).run(replace(corpus, cases=(corpus.cases[0],)), digest="digest")

    assert run.receipts[0].outcome is EvaluationOutcome.CASE_DEADLINE_EXCEEDED


@pytest.mark.parametrize(
    ("outcome", "supported", "completed"),
    (
        (EvaluationOutcome.UNSUPPORTED_DIALOGUE_STEP, 0, 0),
        (EvaluationOutcome.TRANSPORT_ERROR, 0, 0),
        (EvaluationOutcome.REQUEST_TIMEOUT, 0, 0),
        (EvaluationOutcome.CLARIFICATION_REQUESTED, 1, 0),
        (EvaluationOutcome.STRUCTURAL_RESOLUTION, 1, 0),
        (EvaluationOutcome.ASSESSMENT_COMPLETED, 1, 1),
        (EvaluationOutcome.CLARIFICATION_ABSTAINED, 1, 1),
    ),
)
def test_dialogue_metrics_do_not_treat_failures_or_open_turns_as_completed(
    outcome,
    supported,
    completed,
):
    corpus = load_clarification_corpus(CORPUS)
    dialogue_case = next(case for case in corpus.cases if case.mode == "dialogue")
    dialogue_corpus = replace(corpus, cases=(dialogue_case,))

    run = SequentialEvaluationRunner(
        lambda case, *, request_timeout_seconds: CaseExecution(outcome),
        config=EvaluationConfig(),
    ).run(dialogue_corpus, digest="digest")

    assert run.summary.dialogue_supported_cases == supported
    assert run.summary.dialogue_completed_cases == completed


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


def test_runner_rejects_refinement_mode_mismatch_before_resume(tmp_path):
    corpus = load_clarification_corpus(CORPUS)
    path = tmp_path / "receipts.jsonl"
    SequentialEvaluationRunner(
        offline_fixture_executor,
        config=EvaluationConfig(refinement_mode="full_snapshot"),
        receipt_path=path,
    ).run(corpus, digest="digest")

    with pytest.raises(ValueError, match="manifest"):
        SequentialEvaluationRunner(
            offline_fixture_executor,
            config=EvaluationConfig(refinement_mode="typed_delta"),
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
