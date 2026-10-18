from pathlib import Path

from onto4.pipeline import (
    EvaluationConfig,
    EvaluationOutcome,
    run_paired_benchmark,
)
from onto4.pipeline.clarification_corpus import ClarificationCorpus, ClarificationCorpusCase
from onto4.pipeline.clarification_corpus import load_clarification_corpus
from onto4.pipeline.evaluation import CaseExecution
from onto4.pipeline.ab_benchmark import BenchmarkCondition, write_benchmark_report


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
                diagnostics={"clarification_turns": 1},
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
    assert '"corpus_digest"' in report.read_text(encoding="utf-8")


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
