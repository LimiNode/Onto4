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
    discover_sequential_host_question_intents,
    discover_host_question_intents,
    HostQuestionDiscovery,
    DiscoveredQuestionIntent,
    write_dialogue_research_report,
)
from onto4.pipeline.clarification_corpus import ClarificationCorpus, ClarificationCorpusCase
from onto4.pipeline.clarification_corpus import load_clarification_corpus
from onto4.pipeline.dialogue_research import _corpus_binding, _dialogue_status
from onto4.pipeline.evaluation import CaseExecution
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    FixtureClarificationPolicy,
    InterpretationSpace,
    SemanticReading,
)
from onto4.pipeline.orchestration import (
    ClarificationSession,
    ReasoningSession,
    issue_reasoning_clarification,
    start_reasoning_session_per_reading,
)
from onto4.pipeline.interactive import (
    FirstAdmissibleDecisionProvider,
    interactive_decision_profile,
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
                "required_turns": 2,
                "admitted_turns": 2,
                "answered_turns": 2,
                "accepted_refinements": 2,
                "completed_reassessments": 2,
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
    assert payload["metadata"]["structural_preflight_validated"] is False
    assert payload["metadata"]["run_bound_preflight_verified"] is False


def test_structural_preflight_is_not_reported_as_run_bound_execution(tmp_path):
    corpus = _dialogue_corpus()
    manifest = (
        DiscoveredQuestionIntent(
            "single",
            0,
            "Meaning",
            "criterion",
            ("a",),
            corpus_binding=_corpus_binding(corpus),
            snapshot_id="preflight-snapshot-x",
            assessment_id="preflight-assessment-x",
        ),
    )

    def executor_factory(_condition):
        return lambda case, *, request_timeout_seconds: CaseExecution(
            EvaluationOutcome.ASSESSMENT_COMPLETED,
            diagnostics={
                "required_turns": 1,
                "admitted_turns": 1,
                "answered_turns": 1,
                "accepted_refinements": 1,
                "completed_reassessments": 1,
                "questions_issued": 1,
                "answers_consumed": 1,
                "refinement_accepted": True,
                "reassessment_performed": True,
                "clarification_turns": 1,
                "clarification_turns_known": True,
            },
        )

    run = run_bounded_dialogue_research(
        corpus,
        executor_factory=executor_factory,
        config=EvaluationConfig(),
        receipt_dir=tmp_path,
        intent_manifest=manifest,
    )
    assert run.metadata["structural_preflight_validated"] is True
    assert run.metadata["preflight_manifest_digest"]
    assert run.metadata["run_bound_preflight_verified"] is False


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
        DiscoveredQuestionIntent(
            "single",
            0,
            "Ontology",
            "criterion",
            ("a",),
            corpus_binding=_corpus_binding(_dialogue_corpus()),
            snapshot_id="snapshot-0",
            assessment_id="assessment-0",
        ),
    )
    with pytest.raises(ValueError, match="contradict"):
        validate_dialogue_intent_manifest(corpus, manifest)


def test_sequential_preflight_requires_one_question_per_snapshot():
    corpus = _dialogue_corpus()

    def discover(case, index, previous):
        if index:
            assert previous == "snapshot-0"
        return HostQuestionDiscovery(
            questions=(
                ClarificationQuestion(
                    f"q-{index}", ClarificationKind.Meaning, "q", ("a",),
                    target_family="criterion",
                ),
            ),
            snapshot_id=f"snapshot-{index}",
            previous_snapshot_id=previous,
            assessment_id=f"assessment-{index}",
        )

    manifest = discover_sequential_host_question_intents(corpus, discover)
    assert len(manifest) == 1


def test_initial_preflight_rejects_unbound_question_lists():
    with pytest.raises(ValueError, match="provenance"):
        discover_host_question_intents(_dialogue_corpus(), lambda _case: ())


def test_one_completed_turn_cannot_claim_two_turn_dialogue_complete():
    assert (
        _dialogue_status(2, 1, 1, 1, 1, True, True, True, True)
        == "incomplete"
    )


def test_preflight_rejects_foreign_or_duplicate_provenance():
    corpus = _dialogue_corpus()
    binding = _corpus_binding(corpus)
    item = DiscoveredQuestionIntent(
        "foreign", 0, "Meaning", "criterion", ("a",), binding,
        "snapshot", None, "assessment",
    )
    with pytest.raises(ValueError, match="foreign"):
        validate_dialogue_intent_manifest(corpus, (item,))
    assert "criterion" not in item.safe_record().values()


def test_corpus_binding_changes_when_script_or_oracle_changes():
    corpus = _dialogue_corpus()
    changed_case = ClarificationCorpusCase(
        **{**corpus.cases[0].__dict__, "utterance": "Changed claim."}
    )
    changed = ClarificationCorpus(
        version=corpus.version,
        name=corpus.name,
        cases=(changed_case, corpus.cases[1]),
        model_input=corpus.model_input,
        context_profiles=corpus.context_profiles,
    )
    assert _corpus_binding(corpus) != _corpus_binding(changed)


def test_preflight_requires_global_dialogue_coverage_and_unique_snapshots():
    first = _dialogue_corpus().cases[0]
    second = ClarificationCorpusCase(**{**first.__dict__, "case_id": "second"})
    corpus = ClarificationCorpus(
        version=2,
        name="two-dialogues",
        cases=(first, second),
    )
    binding = _corpus_binding(corpus)
    item = DiscoveredQuestionIntent(
        "single", 0, "Meaning", "criterion", ("a",), binding,
        "same-snapshot", None, "assessment-a",
    )
    with pytest.raises(ValueError, match="exactly"):
        validate_dialogue_intent_manifest(corpus, (item,))
    second_item = DiscoveredQuestionIntent(
        "second", 0, "Meaning", "criterion", ("a",), binding,
        "same-snapshot", None, "assessment-b",
    )
    with pytest.raises(ValueError, match="globally unique"):
        validate_dialogue_intent_manifest(corpus, (item, second_item))


def test_dialogue_status_requires_successful_assessment_execution():
    assert _dialogue_status(
        1, 1, 1, 1, 1, True, True, True, True,
        "failed", "assessment_completed",
    ) == "incomplete"
    assert _dialogue_status(
        1, 1, 1, 1, 1, True, True, True, True,
        "successful", "dialogue_incomplete",
    ) == "incomplete"


def test_session_bound_refinement_accepts_real_host_issued_question():
    initial = InterpretationSpace(
        "session-initial",
        "Claim.",
        ConceptualDepth.Philosophical,
        ambiguities=(Ambiguity("ambiguity-0", "identity", "criterion"),),
        readings=(SemanticReading("reading-0", "identity", "identity reading"),),
    )

    class EmptyFormalizer:
        def formalize(self, request):
            return ()

    started = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=EmptyFormalizer(),
        contexts={},
        clarification_policy=FixtureClarificationPolicy(),
    ).session
    issued = issue_reasoning_clarification(
        started,
        profile=interactive_decision_profile(),
        provider=FirstAdmissibleDecisionProvider(),
        clarification_policy=FixtureClarificationPolicy(),
    ).session
    assert issued.clarification.pending is not None

    class FullProvider:
        def refine(self, interpretation, question, answer):
            return InterpretationSpace(
                "full-successor", interpretation.source_text, interpretation.conceptual_depth,
                readings=interpretation.readings,
            )

    class DeltaProvider:
        def propose_refinement_deltas(self, interpretation, question, answer, **boundary):
            return ({
                "operation": "select_reading",
                "target_id": "reading-0",
                "resolved_ambiguity_ids": ["ambiguity-0"],
            },)

    result = run_session_bound_isolated_refinement_pair(
        issued,
        "identity criterion",
        full_snapshot_provider=FullProvider(),
        typed_delta_provider=DeltaProvider(),
    )
    assert result.protocol == "session_bound_isolated_refinement"
    assert [cell.outcome for cell in result.cells] == ["accepted", "accepted"]
    assert all(cell.transition_valid for cell in result.cells)
