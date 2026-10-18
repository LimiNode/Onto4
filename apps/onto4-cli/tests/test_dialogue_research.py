import json
from pathlib import Path

import pytest

from onto4.pipeline import (
    BoundedDialogueResearchRun,
    EvaluationConfig,
    EvaluationOutcome,
    run_bounded_dialogue_research,
    run_model_backed_isolated_refinement_pair,
    run_session_bound_isolated_refinement_pair,
    validate_dialogue_intent_manifest,
    DiscoveredQuestionIntent,
    write_dialogue_research_report,
)
from onto4.pipeline.clarification_corpus import ClarificationCorpus, ClarificationCorpusCase
from onto4.pipeline.clarification_corpus import load_clarification_corpus
from onto4.pipeline.evaluation import CaseExecution
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    InterpretationSpace,
    SemanticReading,
)


def _dialogue_corpus() -> ClarificationCorpus:
    return ClarificationCorpus(
        version=2,
        name="bounded-dialogue",
        cases=(
            ClarificationCorpusCase(
                case_id="single",
                utterance="Claim.",
                context=None,
                hidden_interpretation=None,
                expected_clarification=None,
                expected_after_answer={"disposition": "dialogue_reassessment_required"},
                mode="dialogue",
                dialogue=(
                    {"turn_id": "u0", "role": "user", "text": "Claim."},
                    {
                        "turn_id": "a0",
                        "role": "assistant",
                        "text": "Clarify.",
                        "question_kind": "Meaning",
                        "target_family": "criterion",
                        "target_ids": ["a"],
                    },
                ),
            ),
            ClarificationCorpusCase(
                case_id="control",
                utterance="Control.",
                context=None,
                hidden_interpretation=None,
                expected_clarification=None,
                expected_after_answer={"verdict": "T"},
            ),
        ),
    )


def test_bounded_dialogue_corpus_contains_two_explicit_multi_turn_cases():
    root = Path(__file__).parents[1]
    corpus = load_clarification_corpus(
        root / "eval" / "clarification" / "bounded-dialogue-v1.yaml"
    )
    assert {case.case_id for case in corpus.cases} == {
        "genome-identity-bounded",
        "intrinsic-time-bounded",
    }
    assert all(
        sum(
            turn.get("role") == "assistant" and "question_kind" in turn
            for turn in case.dialogue
        ) == 2
        for case in corpus.cases
    )


def test_bounded_dialogue_research_reports_each_required_stage(tmp_path):
    def executor_factory(_condition):
        return lambda case, *, request_timeout_seconds: CaseExecution(
            EvaluationOutcome.ASSESSMENT_COMPLETED,
            semantic_verdict="T",
            diagnostics={
                "questions_issued": 2,
                "answers_consumed": 2,
                "refinement_accepted": True,
                "reassessment_performed": True,
                "clarification_turns": 2,
                "clarification_turns_known": True,
            },
        )

    run = run_bounded_dialogue_research(
        _dialogue_corpus(),
        executor_factory=executor_factory,
        config=EvaluationConfig(),
        receipt_dir=tmp_path,
    )

    assert isinstance(run, BoundedDialogueResearchRun)
    assert {cell.case_id for cell in run.cells} == {"single"}
    assert all(cell.dialogue_status == "complete" for cell in run.cells)
    assert all(cell.question_issued and cell.answer_consumed for cell in run.cells)
    assert all(
        run.stage_counts[condition]["reassessment_performed"]["true"] == 1
        for condition in ("A1", "A2", "B1", "B2")
    )
    report = tmp_path / "dialogue.json"
    write_dialogue_research_report(run, report)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["record_type"] == "bounded_dialogue_research"
    assert payload["metadata"]["stage_contract"][-1] == "reassessment_performed"


def test_model_backed_isolated_refinement_uses_one_initial_snapshot():
    initial = InterpretationSpace(
        "initial",
        "Claim.",
        ConceptualDepth.Philosophical,
        ambiguities=(Ambiguity("ambiguity-0", "identity", "criterion"),),
        readings=(SemanticReading("reading-0", "identity", "one reading"),),
    )
    question = ClarificationQuestion(
        "meaning:ambiguity-0",
        ClarificationKind.Meaning,
        "Which identity criterion?",
        ("ambiguity-0",),
        target_family="identity",
    )

    class FullProvider:
        def refine(self, interpretation, issued_question, issued_answer):
            assert interpretation is initial
            assert issued_question is question
            assert issued_answer == "numerical identity"
            return InterpretationSpace(
                "full-successor",
                interpretation.source_text,
                interpretation.conceptual_depth,
                readings=interpretation.readings,
            )

    class DeltaProvider:
        def propose_refinement_deltas(self, interpretation, issued_question, issued_answer, **boundary):
            assert interpretation is initial
            assert issued_question is question
            assert issued_answer == "numerical identity"
            return ({
                "operation": "select_reading",
                "target_id": "reading-0",
                "resolved_ambiguity_ids": ["ambiguity-0"],
            },)

    result = run_model_backed_isolated_refinement_pair(
        initial,
        question,
        "numerical identity",
        full_snapshot_provider=FullProvider(),
        typed_delta_provider=DeltaProvider(),
    )

    assert result.initial_snapshot_digest
    assert result.protocol == "provider_isolated_refinement"
    assert [cell.outcome for cell in result.cells] == ["accepted", "accepted"]
    assert all(cell.transition_valid for cell in result.cells)


def test_session_bound_isolated_refinement_rejects_arbitrary_question():
    from onto4.pipeline.orchestration import ClarificationSession, ReasoningSession

    initial = InterpretationSpace(
        "initial", "Claim.", ConceptualDepth.Philosophical
    )
    session = ReasoningSession(ClarificationSession(initial), None)
    with pytest.raises(ValueError, match="current assessment"):
        run_session_bound_isolated_refinement_pair(
            session,
            "answer",
            full_snapshot_provider=object(),
            typed_delta_provider=object(),
        )


def test_intent_manifest_is_checked_without_rewriting_oracle():
    corpus = _dialogue_corpus()
    manifest = (
        DiscoveredQuestionIntent("single", 0, "Ontology", "criterion", ("a",)),
    )
    with pytest.raises(ValueError, match="contradict"):
        validate_dialogue_intent_manifest(corpus, manifest)
