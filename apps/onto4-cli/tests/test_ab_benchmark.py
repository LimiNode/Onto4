import json
from dataclasses import replace
from pathlib import Path

import pytest

from onto4.pipeline import (
    BenchmarkStatus,
    DEFAULT_BENCHMARK_CONDITIONS,
    EvaluationConfig,
    EvaluationOutcome,
    IsolatedRefinementRun,
    rescore_paired_receipts,
    run_isolated_refinement_pair,
    run_paired_benchmark,
)
from onto4.pipeline.clarification_corpus import ClarificationCorpus, ClarificationCorpusCase
from onto4.pipeline.clarification_corpus import load_clarification_corpus
from onto4.pipeline.evaluation import CaseExecution
from onto4.pipeline.ab_benchmark import (
    BenchmarkCondition,
    ReceiptProvenanceError,
    _semantic_obligation_payload,
    _snapshot_digest,
    write_benchmark_report,
)
from onto4.pipeline.evaluation import CaseReceipt
from onto4.reasoning import (
    Ambiguity,
    ClarificationQuestion,
    ClarificationKind,
    ClarificationTurn,
    ConceptualDepth,
    InterpretationSpace,
    Presupposition,
    SemanticReading,
)


def _corpus() -> ClarificationCorpus:
    return ClarificationCorpus(
        version=2,
        name="benchmark-fixture",
        cases=(
            ClarificationCorpusCase(
                case_id="case-t",
                utterance="A philosophical claim.",
                context=None,
                hidden_interpretation=None,
                expected_clarification=None,
                expected_after_answer={"verdict": "T"},
            ),
        ),
    )


def test_paired_benchmark_runs_all_four_cells_and_preserves_pairing(tmp_path):
    corpus = _corpus()

    def executor_factory(condition):
        def execute(case, *, request_timeout_seconds):
            del request_timeout_seconds
            wins = condition.name in {"A1", "A2"}
            return CaseExecution(
                EvaluationOutcome.ASSESSMENT_COMPLETED,
                provider_calls=2,
                semantic_verdict="T" if wins else "F",
                    diagnostics={"clarification_turns": 1, "clarification_turns_known": True},
                stage_details={"formalization": "finish_reason=stop, completion_tokens=7"},
            )

        return execute

    run = run_paired_benchmark(
        corpus,
        executor_factory=executor_factory,
        config=EvaluationConfig(),
        receipt_dir=tmp_path,
        output_cost_per_million=2.0,
    )

    assert set(run.runs) == {"A1", "A2", "B1", "B2"}
    assert len(run.cells) == 4
    assert run.summary.oracle_comparable_observations == 4
    assert run.summary.oracle_passed_observations == 2
    assert run.summary.semantic_errors == 2
    assert run.summary.pair_wins == {
        "A1_vs_B1": {"A1": 1, "B1": 0, "tie": 0},
        "A2_vs_B2": {"A2": 1, "B2": 0, "tie": 0},
        "A1_vs_A2": {"A1": 0, "A2": 0, "tie": 1},
        "B1_vs_B2": {"B1": 0, "B2": 0, "tie": 1},
    }
    assert run.summary.provider_calls == {name: 2 for name in run.runs}
    assert run.summary.completion_tokens == {name: 7 for name in run.runs}
    assert run.summary.estimated_output_cost_usd == {
        name: 0.000014 for name in run.runs
    }
    assert all((tmp_path / f"{name}.receipts.jsonl").exists() for name in run.runs)

    report = tmp_path / "benchmark.json"
    write_benchmark_report(run, report)
    payload = report.read_text(encoding="utf-8")
    assert '"corpus_digest"' in payload
    assert '"run_configs"' in payload
    assert '"A2_vs_B2"' in payload


def test_execution_failure_is_unverified_and_not_a_semantic_error():
    corpus = _corpus()

    def executor_factory(_condition):
        return lambda case, *, request_timeout_seconds: CaseExecution(
            EvaluationOutcome.SCHEMA_INVALID,
            semantic_verdict="T",
            diagnostics={"clarification_turns_known": False},
        )

    run = run_paired_benchmark(
        corpus,
        executor_factory=executor_factory,
        config=EvaluationConfig(),
    )

    assert all(cell.semantic_status == BenchmarkStatus.UNVERIFIED.value for cell in run.cells)
    assert run.summary.semantic_errors == 0
    assert run.summary.operational_failures == 4


def test_dialogue_incomplete_does_not_count_as_reassessment_success():
    corpus = ClarificationCorpus(
        version=2,
        name="dialogue-oracle",
        cases=(
            ClarificationCorpusCase(
                case_id="dialogue",
                utterance="Claim.",
                context=None,
                hidden_interpretation=None,
                expected_clarification={"kind": "Meaning"},
                expected_after_answer={"disposition": "dialogue_reassessment_required"},
                mode="dialogue",
            ),
        ),
    )

    def executor_factory(_condition):
        return lambda case, *, request_timeout_seconds: CaseExecution(
            EvaluationOutcome.DIALOGUE_INCOMPLETE,
            diagnostics={
                "questions_issued": 1,
                "answers_consumed": 1,
                "refinement_accepted": True,
                "reassessment_performed": False,
                "question_kind": "Meaning",
                "clarification_turns_known": False,
            },
        )

    run = run_paired_benchmark(corpus, executor_factory=executor_factory, config=EvaluationConfig())
    assert all(cell.workflow_status == BenchmarkStatus.INCORRECT.value for cell in run.cells)
    assert all(cell.semantic_status == BenchmarkStatus.NOT_COMPARABLE.value for cell in run.cells)
    assert run.summary.semantic_errors == 0


def test_missing_semantic_oracle_is_not_comparable():
    corpus = ClarificationCorpus(
        version=2,
        name="no-semantic-oracle",
        cases=(
            ClarificationCorpusCase(
                case_id="no-oracle",
                utterance="Claim.",
                context=None,
                hidden_interpretation=None,
                expected_clarification=None,
                expected_after_answer={},
            ),
        ),
    )
    run = run_paired_benchmark(
        corpus,
        executor_factory=lambda _condition: (
            lambda case, *, request_timeout_seconds: CaseExecution(
                EvaluationOutcome.ASSESSMENT_COMPLETED,
                diagnostics={"clarification_turns": 0, "clarification_turns_known": True},
            )
        ),
        config=EvaluationConfig(),
    )
    assert all(cell.semantic_status == BenchmarkStatus.NOT_COMPARABLE.value for cell in run.cells)
    assert run.summary.semantic_errors == 0
    assert all(value is None for value in run.summary.estimated_output_cost_usd.values())


def test_rescore_existing_receipts_without_provider_calls(tmp_path):
    run = run_paired_benchmark(
        _corpus(),
        executor_factory=lambda _condition: (
            lambda case, *, request_timeout_seconds: CaseExecution(
                EvaluationOutcome.ASSESSMENT_COMPLETED,
                semantic_verdict="T",
                diagnostics={"clarification_turns": 0, "clarification_turns_known": True},
            )
        ),
        config=EvaluationConfig(),
        receipt_dir=tmp_path,
    )
    rescored = rescore_paired_receipts(_corpus(), tmp_path)
    assert rescored.summary.semantic_errors == run.summary.semantic_errors == 0
    assert rescored.metadata["benchmark_type"] == "e2e_paired_by_case_rescore"


def test_e2e_runner_requires_the_complete_four_cell_design():
    with pytest.raises(ValueError, match="requires exactly A1"):
        run_paired_benchmark(
            _corpus(),
            executor_factory=lambda _condition: (
                lambda case, *, request_timeout_seconds: CaseExecution(
                    EvaluationOutcome.ASSESSMENT_COMPLETED
                )
            ),
            config=EvaluationConfig(),
            conditions=DEFAULT_BENCHMARK_CONDITIONS[:3],
        )


def test_e2e_runner_rejects_condition_label_with_wrong_semantics():
    conditions = list(DEFAULT_BENCHMARK_CONDITIONS)
    conditions[0] = BenchmarkCondition("A1", "context_aware", "typed_delta")
    with pytest.raises(ValueError, match="Condition A1"):
        run_paired_benchmark(
            _corpus(),
            executor_factory=lambda _condition: (
                lambda case, *, request_timeout_seconds: CaseExecution(
                    EvaluationOutcome.ASSESSMENT_COMPLETED
                )
            ),
            config=EvaluationConfig(),
            conditions=tuple(conditions),
        )


def test_workflow_false_is_not_hidden_by_missing_secondary_check():
    corpus = ClarificationCorpus(
        version=2,
        name="workflow-tristate",
        cases=(
            ClarificationCorpusCase(
                case_id="case",
                utterance="Claim.",
                context=None,
                hidden_interpretation=None,
                expected_clarification={"kind": "Meaning", "target_family": "SECRET_USER_SOURCE_123"},
                expected_after_answer={"disposition": "clarification_required"},
            ),
        ),
    )

    def executor_factory(_condition):
        return lambda case, *, request_timeout_seconds: CaseExecution(
            EvaluationOutcome.ASSESSMENT_COMPLETED,
            diagnostics={"question_kind": "Ontology"},
        )

    run = run_paired_benchmark(corpus, executor_factory=executor_factory, config=EvaluationConfig())
    assert all(cell.workflow_status == BenchmarkStatus.INCORRECT.value for cell in run.cells)
    payload = json.dumps([cell.workflow_diagnostics for cell in run.cells])
    assert "SECRET_USER_SOURCE_123" not in payload


def test_semantic_digest_includes_reading_presupposition_bindings():
    presuppositions = (
        # IDs are intentionally opaque; only semantic content should bind.
        Presupposition("p1", "A stable object"),
        Presupposition("p2", "A continuing process"),
    )
    left = InterpretationSpace(
        "left", "Claim.", ConceptualDepth.Philosophical,
        presuppositions=presuppositions,
        readings=(SemanticReading("r1", "one", "one", ("p1",)),),
    )
    right = replace(
        left,
        id="right",
        readings=(SemanticReading("r1", "one", "one", ("p2",)),),
    )
    assert _semantic_obligation_payload(left)["readings"][0]["presupposition_count"] == 1
    assert _snapshot_digest(left) != _snapshot_digest(right)


def test_rescore_rejects_legacy_receipts(tmp_path):
    run_paired_benchmark(
        _corpus(),
        executor_factory=lambda _condition: (
            lambda case, *, request_timeout_seconds: CaseExecution(EvaluationOutcome.ASSESSMENT_COMPLETED)
        ),
        config=EvaluationConfig(),
        receipt_dir=tmp_path,
    )
    manifest_path = tmp_path / "A1.receipts.jsonl"
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    manifest = json.loads(lines[0])
    manifest.pop("manifest_schema_version")
    manifest_path.write_text("\n".join([json.dumps(manifest), *lines[1:]]) + "\n", encoding="utf-8")
    with pytest.raises(ReceiptProvenanceError, match="legacy_missing_metadata"):
        rescore_paired_receipts(_corpus(), tmp_path)


def test_isolated_refinement_pair_uses_one_initial_snapshot_and_validates_provenance():
    initial = InterpretationSpace(
        "initial",
        "Claim.",
        ConceptualDepth.Philosophical,
        ambiguities=(Ambiguity("ambiguity-0", "same", "identity"),),
    )
    question = ClarificationQuestion(
        "meaning:ambiguity-0",
        ClarificationKind.Meaning,
        "Clarify.",
        ("ambiguity-0",),
        target_family="same",
    )

    def transition(same_initial, same_question, answer):
        assert same_initial is initial
        assert same_question is question
        successor = InterpretationSpace("successor", same_initial.source_text, same_initial.conceptual_depth)
        return successor, ClarificationTurn(initial.id, question.id, answer, successor.id)

    isolated = run_isolated_refinement_pair(
        initial,
        question,
        "same individual",
        full_snapshot=transition,
        typed_delta=transition,
        case_id="identity",
    )
    assert isinstance(isolated, IsolatedRefinementRun)
    assert isolated.initial_snapshot_digest
    assert [cell.outcome for cell in isolated.cells] == ["accepted", "accepted"]
    assert isolated.cells[0].semantic_obligation_digest == isolated.cells[1].semantic_obligation_digest


def test_philosophical_smoke_corpus_is_executable_and_has_two_dialogues():
    root = Path(__file__).parents[1]
    corpus = load_clarification_corpus(
        root / "eval" / "clarification" / "ab-philosophical-smoke.yaml"
    )

    assert corpus.name == "ab-philosophical-smoke"
    assert corpus.model_input == "contextual"
    assert len(corpus.cases) == 4
    assert sum(case.mode == "dialogue" for case in corpus.cases) == 2
    assert {case.context for case in corpus.cases} == {
        "continuity",
        "substance",
        "identity_and_genome",
        "relational_time",
    }
