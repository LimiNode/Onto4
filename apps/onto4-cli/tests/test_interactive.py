from dataclasses import dataclass, replace

import pytest

from onto4.core import AssessmentContext, OntologyProfile, PredicateCall, PredicateExpr, PredicateSignature, Verdict
from onto4.core.evidence import AtomicVerdictStore
from onto4.pipeline import (
    ClarificationProgressKind,
    ClarificationSession,
    FirstAdmissibleDecisionProvider,
    ModelClarificationPolicy,
    ProgressAwareClarificationPolicy,
    TypedDeltaClarificationPolicy,
    answer_reasoning_clarification,
    interactive_decision_profile,
    issue_reasoning_clarification,
    run_interactive_dialogue,
    start_reasoning_session_per_reading,
)
from onto4.pipeline.interactive import _classify_progress
from onto4.providers import FormalizationRequest, InterpretationRequest
from onto4.reasoning import (
    Ambiguity,
    AssessmentLandscape,
    ClarificationContext,
    ClarificationKind,
    ClarificationQuestion,
    ClarificationTurn,
    ConceptualDepth,
    CrossCandidateStatus,
    FixtureClarificationPolicy,
    FormalizationCandidate,
    InterpretationSpace,
    OntologyCandidate,
    Presupposition,
    SemanticReading,
)


def _context() -> AssessmentContext:
    return AssessmentContext(
        ontology=OntologyProfile(
            name="identity",
            predicates={"identity_claim": PredicateSignature(())},
        ),
        verdicts=AtomicVerdictStore({"identity_claim()": Verdict.T}),
    )


def _space(identifier: str, *, ambiguous: bool) -> InterpretationSpace:
    return InterpretationSpace(
        id=identifier,
        source_text="Настоящая личность человека определяется его генами.",
        conceptual_depth=ConceptualDepth.Ordinary,
        ambiguities=(
            (Ambiguity("ambiguity-0", "определяется", "влияние или носитель сущности"),)
            if ambiguous
            else ()
        ),
        readings=(SemanticReading("reading-0", "identity", "identity claim"),),
    )


class _InterpretationProvider:
    def __init__(self, initial: InterpretationSpace):
        self.initial = initial

    def interpret(self, request: InterpretationRequest) -> InterpretationSpace:
        assert request.source_text == self.initial.source_text
        return self.initial


class _FormalizationProvider:
    def formalize(self, request: FormalizationRequest):
        assert request.reading is not None
        assert request.context_id == "identity"
        return (
            FormalizationCandidate(
                id=f"candidate:{request.interpretation.id}",
                label=request.reading.label,
                formalization_id="identity-formalization",
                context_id="identity",
                reading_id=request.reading.id,
                formalization=PredicateExpr(PredicateCall("identity_claim", ())),
            ),
        )


@dataclass
class _RefinementProvider:
    successor: InterpretationSpace
    calls: int = 0

    def refine(self, interpretation, question, answer):
        self.calls += 1
        assert interpretation.ambiguities
        assert question.kind is ClarificationKind.Meaning
        assert answer == "Гены содержат то, чем человек является на самом деле."
        return self.successor


def test_interactive_dialogue_uses_successor_and_reassessment():
    initial = _space("initial", ambiguous=True)
    successor = _space("successor", ambiguous=False)
    refinement = _RefinementProvider(successor)
    output = []

    result = run_interactive_dialogue(
        InterpretationRequest(initial.source_text),
        interpretation_provider=_InterpretationProvider(initial),
        refinement_provider=refinement,
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=ModelClarificationPolicy(
            FixtureClarificationPolicy(), refinement
        ),
        input_fn=lambda prompt: "Гены содержат то, чем человек является на самом деле.",
        output_fn=output.append,
        max_turns=2,
    )

    assert result.turns == 1
    assert result.session.clarification.interpretation is successor
    assert result.session.assessment is not None
    assert result.session.assessment.ask_result.disposition.value == "Complete"
    assert refinement.calls == 1
    assert any("Clarification:" in line for line in output)
    assert result.progress.entries[0].kind is ClarificationProgressKind.StructuralResolution


def test_interactive_dialogue_executes_two_host_transitions_without_duplicate_history():
    initial = InterpretationSpace(
        id="initial-two-turn",
        source_text="Claim.",
        conceptual_depth=ConceptualDepth.Ordinary,
        ambiguities=(
            Ambiguity("ambiguity-0", "identity", "first criterion"),
            Ambiguity("ambiguity-1", "continuity", "second criterion"),
        ),
        readings=(SemanticReading("reading-0", "identity", "identity claim"),),
    )
    first = InterpretationSpace(
        id="successor-one",
        source_text=initial.source_text,
        conceptual_depth=initial.conceptual_depth,
        ambiguities=(initial.ambiguities[1],),
        readings=initial.readings,
    )
    second = InterpretationSpace(
        id="successor-two",
        source_text=initial.source_text,
        conceptual_depth=initial.conceptual_depth,
        readings=initial.readings,
    )

    class TwoStepRefinement:
        def __init__(self):
            self.calls = []

        def refine(self, interpretation, question, answer):
            self.calls.append((interpretation.id, question.id, answer))
            return first if len(self.calls) == 1 else second

    refinement = TwoStepRefinement()
    answers = iter(("first answer", "second answer"))
    result = run_interactive_dialogue(
        InterpretationRequest(initial.source_text),
        interpretation_provider=_InterpretationProvider(initial),
        refinement_provider=refinement,
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=ModelClarificationPolicy(
            FixtureClarificationPolicy(), refinement
        ),
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _line: None,
        max_turns=3,
    )

    assert result.stop_reason == "complete"
    assert result.turns == 2
    assert len(result.progress.entries) == 2
    assert len(result.session.clarification.history.turns) == 2
    assert [turn.previous_interpretation_id for turn in result.session.clarification.history.turns] == [
        "initial-two-turn", "successor-one"
    ]
    assert [turn.successor_interpretation_id for turn in result.session.clarification.history.turns] == [
        "successor-one", "successor-two"
    ]
    assert len(refinement.calls) == 2


def test_stable_target_binding_ignores_model_wording_but_keeps_goals_distinct():
    def context_for(space):
        return ClarificationContext(
            interpretation=space,
            candidates=(),
            assessments=(),
            landscape=AssessmentLandscape(
                (), CrossCandidateStatus.FormalizationUnresolved
            ),
        )

    same_goal = FixtureClarificationPolicy(
        ambiguity_target_families={
            "ambiguity-a": "identity-criterion",
            "ambiguity-b": "identity-criterion",
        },
        require_ambiguity_target_families=True,
    )
    first = InterpretationSpace(
        "wording-a", "Claim.", ConceptualDepth.Ordinary,
        ambiguities=(Ambiguity("ambiguity-a", "model wording one", "meaning"),),
    )
    second = InterpretationSpace(
        "wording-b", "Claim.", ConceptualDepth.Ordinary,
        ambiguities=(Ambiguity("ambiguity-b", "model wording two", "meaning"),),
    )
    first_question = same_goal.choose(context_for(first))
    second_question = same_goal.choose(context_for(second))
    assert first_question is not None and second_question is not None
    assert first_question.target_family == second_question.target_family == (
        "identity-criterion"
    )

    different_goal = FixtureClarificationPolicy(
        ambiguity_target_families={
            "ambiguity-a": "identity-criterion",
            "ambiguity-b": "intrinsic-time",
        },
        require_ambiguity_target_families=True,
    )
    different_question = different_goal.choose(context_for(second))
    assert different_question is not None
    assert different_question.target_family != first_question.target_family


def test_typed_delta_dialogue_uses_same_question_and_host_applies_operation():
    initial = _space("initial", ambiguous=True)
    proposals = []

    class DeltaProvider:
        def propose_refinement_deltas(
            self,
            interpretation,
            question,
            answer,
            **boundary,
        ):
            proposals.append((interpretation, question, answer, boundary))
            return (
                {
                    "operation": "select_reading",
                    "target_id": "reading-0",
                    "resolved_ambiguity_ids": ["ambiguity-0"],
                },
                {
                    "operation": "add_presupposition",
                    "reading_id": "reading-0",
                    "description": "genes are treated as an identity bearer",
                },
            )

    policy = TypedDeltaClarificationPolicy(
        FixtureClarificationPolicy(), DeltaProvider()
    )
    answer = "Genes carry the person's identity."
    result = run_interactive_dialogue(
        InterpretationRequest(initial.source_text),
        interpretation_provider=_InterpretationProvider(initial),
        refinement_provider=_RefinementProvider(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=policy,
        input_fn=lambda prompt: answer,
        output_fn=lambda line: None,
        max_turns=2,
    )

    successor = result.session.clarification.interpretation
    assert successor.id.startswith("interpretation-")
    assert successor.source_text == initial.source_text
    assert successor.conceptual_depth is initial.conceptual_depth
    assert successor.ambiguities == ()
    assert successor.readings[0].id == initial.readings[0].id
    assert successor.presuppositions[-1].description == (
        "genes are treated as an identity bearer"
    )
    assert successor.readings[0].presupposition_ids == ("presupposition-0",)
    assert proposals[0][1].id == "meaning:ambiguity-0"
    assert proposals[0][2] == answer
    assert proposals[0][3]["allowed_reading_ids"] == ("reading-0",)
    assert proposals[0][3]["allowed_ambiguity_ids"] == ("ambiguity-0",)


def test_typed_delta_rejects_forged_target_without_publishing_successor():
    initial = _space("initial", ambiguous=True)

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            return ({
                "operation": "select_reading",
                "target_id": "model-invented",
                "resolved_ambiguity_ids": ["ambiguity-0"],
            },)

    policy = TypedDeltaClarificationPolicy(
        FixtureClarificationPolicy(), DeltaProvider()
    )
    question = FixtureClarificationPolicy().choose(
        start_reasoning_session_per_reading(
            ClarificationSession(initial),
            formalization_provider=_FormalizationProvider(),
            contexts={"identity": _context()},
            clarification_policy=FixtureClarificationPolicy(),
        ).session.assessment.clarification_context()
    )

    with pytest.raises(ValueError, match="Unknown or inadmissible reading target"):
        policy.successor(
            interpretation=initial,
            question=question,
            answer="invented reading",
        )


def test_typed_delta_rejects_mixed_abstention_atomically():
    initial = _space("initial", ambiguous=True)

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            return (
                {
                    "operation": "select_reading",
                    "target_id": "reading-0",
                    "resolved_ambiguity_ids": ["ambiguity-0"],
                },
                {"operation": "abstain", "reason": "uncertain"},
            )

    policy = TypedDeltaClarificationPolicy(
        FixtureClarificationPolicy(), DeltaProvider()
    )
    assessment = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=FixtureClarificationPolicy(),
    ).session.assessment
    question = FixtureClarificationPolicy().choose(
        assessment.clarification_context()
    )

    with pytest.raises(ValueError, match="ABSTAIN cannot be combined"):
        policy.successor(
            interpretation=initial,
            question=question,
            answer="physical reading, but uncertain",
        )

    assert initial.id == "initial"
    assert [item.id for item in initial.readings] == ["reading-0"]
    assert [item.id for item in initial.ambiguities] == ["ambiguity-0"]


def test_typed_delta_batch_failure_does_not_publish_partial_successor():
    initial = _space("initial", ambiguous=True)

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            return (
                {
                    "operation": "select_reading",
                    "target_id": "reading-0",
                    "resolved_ambiguity_ids": ["ambiguity-0"],
                },
                {
                    "operation": "refine_ambiguity",
                    "target_id": "ambiguity-0",
                    "text": "identity",
                    "description": "identity bearer",
                },
            )

    policy = TypedDeltaClarificationPolicy(
        FixtureClarificationPolicy(), DeltaProvider()
    )
    assessment = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=FixtureClarificationPolicy(),
    ).session.assessment
    question = FixtureClarificationPolicy().choose(
        assessment.clarification_context()
    )

    with pytest.raises(ValueError, match="Unknown or inadmissible ambiguity target"):
        policy.successor(
            interpretation=initial,
            question=question,
            answer="identity bearer",
        )

    assert initial.id == "initial"
    assert [item.id for item in initial.readings] == ["reading-0"]
    assert [item.id for item in initial.ambiguities] == ["ambiguity-0"]


def test_typed_delta_model_abstain_is_admitted_as_abstained():
    initial = _space("initial", ambiguous=True)

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            return ({"operation": "abstain", "reason": "no safe choice"},)

    policy = TypedDeltaClarificationPolicy(
        FixtureClarificationPolicy(), DeltaProvider()
    )
    assessment = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=FixtureClarificationPolicy(),
    ).session.assessment
    question = FixtureClarificationPolicy().choose(
        assessment.clarification_context()
    )
    progress_policy = ProgressAwareClarificationPolicy(policy)

    successor, _ = progress_policy.successor(
        interpretation=initial,
        question=question,
        answer="I cannot choose between these meanings.",
    )

    assert successor is initial
    assert progress_policy.ledger.entries[0].kind is ClarificationProgressKind.Abstained
    assert progress_policy.ledger.entries[0].refinement_operations == ("abstain",)


def test_typed_delta_retain_ambiguity_is_admitted_as_retained():
    initial = _space("initial", ambiguous=True)

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            return ({
                "operation": "retain_ambiguity",
                "target_id": "ambiguity-0",
                "reason": "answer leaves both readings open",
            },)

    policy = ProgressAwareClarificationPolicy(
        TypedDeltaClarificationPolicy(FixtureClarificationPolicy(), DeltaProvider())
    )
    assessment = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=FixtureClarificationPolicy(),
    ).session.assessment
    question = FixtureClarificationPolicy().choose(
        assessment.clarification_context()
    )

    successor, _ = policy.successor(
        interpretation=initial,
        question=question,
        answer="Both meanings remain possible.",
    )

    assert successor is initial
    assert policy.ledger.entries[0].kind is ClarificationProgressKind.Retained


def test_typed_delta_attached_add_presupposition_is_admitted_as_new_content():
    initial = _space("initial", ambiguous=True)

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            return ({
                "operation": "add_presupposition",
                "reading_id": "reading-0",
                "description": "the speaker commits to an identity bearer",
            },)

    policy = ProgressAwareClarificationPolicy(
        TypedDeltaClarificationPolicy(FixtureClarificationPolicy(), DeltaProvider())
    )
    assessment = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=FixtureClarificationPolicy(),
    ).session.assessment
    question = FixtureClarificationPolicy().choose(
        assessment.clarification_context()
    )

    successor, _ = policy.successor(
        interpretation=initial,
        question=question,
        answer="Genes carry the person's identity.",
    )

    assert successor.readings[0].presupposition_ids == ("presupposition-0",)
    assert policy.ledger.entries[0].kind is ClarificationProgressKind.New
    assert policy.ledger.entries[0].refinement_committed is True


def test_typed_delta_refine_ambiguity_is_unresolved_not_structural_resolution():
    initial = _space("initial", ambiguous=True)

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            return ({
                "operation": "refine_ambiguity",
                "target_id": "ambiguity-0",
                "text": "term",
                "description": "one more specific formulation",
            },)

    policy = ProgressAwareClarificationPolicy(
        TypedDeltaClarificationPolicy(FixtureClarificationPolicy(), DeltaProvider())
    )
    question = ClarificationQuestion(
        "meaning:ambiguity-0",
        ClarificationKind.Meaning,
        "What does the term mean?",
        ("ambiguity-0",),
    )

    policy.successor(interpretation=initial, question=question, answer="clarify")

    assert policy.ledger.entries[0].kind is ClarificationProgressKind.Unresolved


def test_typed_delta_qualify_ontology_is_unresolved_not_ontology_selection():
    initial = replace(
        _space("initial", ambiguous=False),
        ontologies=(
            OntologyCandidate("ontology-0", "ordinary", "ordinary objects"),
        ),
    )

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            return ({
                "operation": "qualify_ontology_candidate",
                "target_id": "ontology-0",
                "description": "a more specific ontology description",
            },)

    policy = ProgressAwareClarificationPolicy(
        TypedDeltaClarificationPolicy(FixtureClarificationPolicy(), DeltaProvider())
    )
    question = ClarificationQuestion(
        "ontology:ontology-0",
        ClarificationKind.Ontology,
        "Which ontology is intended?",
        ("ontology-0",),
    )

    policy.successor(interpretation=initial, question=question, answer="clarify")

    assert policy.ledger.entries[0].kind is ClarificationProgressKind.Unresolved


def test_typed_delta_none_of_the_above_abstains_without_model_call():
    initial = _space("initial", ambiguous=True)

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **kwargs):
            raise AssertionError("none_of_the_above must remain host-controlled")

    policy = TypedDeltaClarificationPolicy(
        FixtureClarificationPolicy(), DeltaProvider()
    )
    assessment = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=FixtureClarificationPolicy(),
    ).session.assessment
    question = FixtureClarificationPolicy().choose(
        assessment.clarification_context()
    )

    successor, turn = policy.successor(
        interpretation=initial,
        question=question,
        answer="none_of_the_above",
    )

    assert successor is initial
    assert turn.successor_interpretation_id == initial.id


def test_typed_delta_marks_unrelated_question_unsupported():
    initial = _space("initial", ambiguous=False)
    boundaries = []

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **boundary):
            boundaries.append(boundary)
            return ({"operation": "abstain", "reason": "unsupported target"},)

    policy = TypedDeltaClarificationPolicy(
        FixtureClarificationPolicy(), DeltaProvider()
    )
    question = ClarificationQuestion(
        "context:disambiguate",
        ClarificationKind.Context,
        "Which context?",
        ("context-a", "context-b"),
        ("context-a", "context-b"),
        "context",
    )

    with pytest.raises(ValueError, match="does not support clarification kind"):
        policy.successor(
            interpretation=initial,
            question=question,
            answer="context-a",
        )
    assert boundaries == []


def test_interactive_dialogue_completes_two_question_fixture_loop():
    initial = replace(
        _space("initial", ambiguous=True),
        ambiguities=(
            Ambiguity("ambiguity-0", "term-a", "first distinction"),
            Ambiguity("ambiguity-1", "term-b", "second distinction"),
        ),
    )
    first_successor = replace(
        initial,
        id="successor-1",
        ambiguities=(initial.ambiguities[1],),
    )
    final_successor = replace(first_successor, id="successor-2", ambiguities=())

    class _TwoStepRefinement:
        def __init__(self):
            self.calls = 0

        def refine(self, interpretation, question, answer):
            self.calls += 1
            return (first_successor, final_successor)[self.calls - 1]

    refinement = _TwoStepRefinement()
    answers = iter(("first answer", "second answer"))
    result = run_interactive_dialogue(
        InterpretationRequest(initial.source_text),
        interpretation_provider=_InterpretationProvider(initial),
        refinement_provider=refinement,
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=ModelClarificationPolicy(
            FixtureClarificationPolicy(), refinement
        ),
        input_fn=lambda prompt: next(answers),
        output_fn=lambda line: None,
        max_turns=2,
    )

    assert result.stop_reason == "complete"
    assert result.turns == 2
    assert result.session.clarification.interpretation is final_successor
    assert len(result.session.clarification.history.turns) == 2
    assert len(result.progress.entries) == 2
    assert refinement.calls == 2


def test_interactive_dialogue_stops_cleanly_after_none_of_the_above():
    initial = _space("initial", ambiguous=True)
    refinement = _RefinementProvider(_space("unused", ambiguous=False))
    output = []

    result = run_interactive_dialogue(
        InterpretationRequest(initial.source_text),
        interpretation_provider=_InterpretationProvider(initial),
        refinement_provider=refinement,
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=ModelClarificationPolicy(
            FixtureClarificationPolicy(), refinement
        ),
        input_fn=lambda prompt: "none_of_the_above",
        output_fn=output.append,
        max_turns=2,
    )

    assert result.stop_reason == "no_new_admissible_question"
    assert result.turns == 1
    assert result.session.clarification.interpretation is initial
    assert len(result.session.clarification.history.turns) == 1
    assert result.session.assessment is not None
    assert result.progress.entries[0].kind is ClarificationProgressKind.Abstained
    assert refinement.calls == 0


def test_interactive_dialogue_reports_max_turns_without_throwing():
    initial = _space("initial", ambiguous=True)
    successor = replace(
        _space("successor", ambiguous=True),
        ambiguities=(Ambiguity("ambiguity-1", "определяется", "новое различение"),),
    )

    class _RepeatRefinement:
        def refine(self, interpretation, question, answer):
            return successor

    refinement = _RepeatRefinement()

    result = run_interactive_dialogue(
        InterpretationRequest(initial.source_text),
        interpretation_provider=_InterpretationProvider(initial),
        refinement_provider=refinement,
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=ModelClarificationPolicy(
            FixtureClarificationPolicy(), refinement
        ),
        input_fn=lambda prompt: "a free-form answer",
        output_fn=lambda line: None,
        max_turns=1,
    )

    assert result.stop_reason == "max_turns_reached"
    assert result.turns == 1
    assert result.session.assessment is not None


def test_none_of_the_above_preserves_snapshot_without_calling_refinement():
    initial = _space("initial", ambiguous=True)
    successor = _space("successor", ambiguous=False)
    refinement = _RefinementProvider(successor)
    policy = ModelClarificationPolicy(FixtureClarificationPolicy(), refinement)
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Что именно означает «определяется»?",
        target_ids=("ambiguity-0",),
    )

    next_space, turn = policy.successor(
        interpretation=initial,
        question=question,
        answer="Ни один вариант мне не подходит.",
    )

    assert next_space is initial
    assert turn.successor_interpretation_id == initial.id
    assert refinement.calls == 0


def test_progress_policy_rejects_changed_snapshot_that_ignores_target():
    initial = _space("initial", ambiguous=True)
    unrelated = InterpretationSpace(
        id="unrelated",
        source_text=initial.source_text,
        conceptual_depth=initial.conceptual_depth,
        ambiguities=initial.ambiguities,
        presuppositions=(Presupposition("presupposition-0", "new premise"),),
        readings=initial.readings,
    )
    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(
            FixtureClarificationPolicy(), _RefinementProvider(unrelated)
        )
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Что именно означает «определяется»?",
        target_ids=("ambiguity-0",),
    )

    with pytest.raises(ValueError, match="did not affect its target distinction"):
        policy.successor(
            interpretation=initial,
            question=question,
            answer="Гены содержат то, чем человек является на самом деле.",
        )


def test_progress_policy_records_abstention_and_blocks_repeat_question():
    initial = _space("initial", ambiguous=True)
    refinement = _RefinementProvider(_space("successor", ambiguous=False))
    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(FixtureClarificationPolicy(), refinement)
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Что именно означает «определяется»?",
        target_ids=("ambiguity-0",),
    )

    successor, _ = policy.successor(
        interpretation=initial,
        question=question,
        answer="Ни один вариант мне не подходит.",
    )

    assert successor is initial
    assert policy.ledger.entries[0].kind is ClarificationProgressKind.Abstained
    context = type("Context", (), {"interpretation": initial, "landscape": None})
    assert policy.choose(context) is None


def test_progress_policy_rejects_no_effect_and_unverifiable_targets():
    initial = _space("initial", ambiguous=True)
    no_effect_policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(
            FixtureClarificationPolicy(), _RefinementProvider(initial)
        )
    )
    meaning_question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Что означает «определяется»?",
        target_ids=("ambiguity-0",),
    )

    with pytest.raises(ValueError, match="progress=no_effect"):
        no_effect_policy.successor(
            interpretation=initial,
            question=meaning_question,
            answer="Гены содержат то, чем человек является на самом деле.",
        )

    changed = _space("changed", ambiguous=False)
    unverified_policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(
            FixtureClarificationPolicy(), _RefinementProvider(changed)
        )
    )
    external_question = ClarificationQuestion(
        id="formalization:candidate-0",
        kind=ClarificationKind.Meaning,
        text="Как понимать формализацию?",
        target_ids=("candidate-0",),
    )

    with pytest.raises(ValueError, match="progress=unverified"):
        unverified_policy.successor(
            interpretation=initial,
            question=external_question,
            answer="Гены содержат то, чем человек является на самом деле.",
        )


def test_reasoning_session_rejects_no_effect_without_mutating_state():
    initial = _space("initial", ambiguous=True)

    class _ReturnSame:
        def refine(self, interpretation, question, answer):
            return interpretation

    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(
            FixtureClarificationPolicy(), _ReturnSame()
        )
    )
    started = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=policy,
    ).session
    issued = issue_reasoning_clarification(
        started,
        profile=interactive_decision_profile(),
        provider=FirstAdmissibleDecisionProvider(),
        clarification_policy=policy,
    ).session
    ledger_before = policy.ledger

    with pytest.raises(ValueError, match="progress=no_effect"):
        answer_reasoning_clarification(
            issued,
            answer="an answer",
            clarification_policy=policy,
        )

    assert issued.clarification.interpretation is initial
    assert issued.clarification.pending is not None
    assert issued.clarification.history.turns == ()
    assert issued.assessment is started.assessment
    assert policy.ledger is ledger_before


def test_reasoning_session_rejects_malformed_turn_before_ledger_commit():
    initial = _space("initial", ambiguous=True)
    successor = replace(initial, id="successor", ambiguities=())

    class _MalformedPolicy:
        def __init__(self):
            self.fixture = FixtureClarificationPolicy()

        def questions(self, context):
            return self.fixture.questions(context)

        def choose(self, context):
            return self.fixture.choose(context)

        def choose_for_kind(self, context, kind):
            return self.fixture.choose_for_kind(context, kind)

        def successor(self, *, interpretation, question, answer):
            return (
                successor,
                type(
                    "MalformedTurn",
                    (),
                    {
                        "previous_interpretation_id": interpretation.id,
                        "question_id": "wrong-question-id",
                        "answer": answer,
                        "successor_interpretation_id": successor.id,
                    },
                )(),
            )

    policy = ProgressAwareClarificationPolicy(_MalformedPolicy())
    started = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        clarification_policy=policy,
    ).session
    issued = issue_reasoning_clarification(
        started,
        profile=interactive_decision_profile(),
        provider=FirstAdmissibleDecisionProvider(),
        clarification_policy=policy,
    ).session
    ledger_before = policy.ledger

    with pytest.raises(ValueError, match="inconsistent turn provenance"):
        answer_reasoning_clarification(
            issued,
            answer="a free-form answer",
            clarification_policy=policy,
            allow_freeform_answers=True,
        )

    assert policy.ledger is ledger_before
    assert issued.clarification.pending is not None
    assert issued.clarification.history.turns == ()


def test_progress_can_resolve_target_and_record_new_semantic_items():
    initial = _space("initial", ambiguous=True)
    successor = InterpretationSpace(
        id="successor",
        source_text=initial.source_text,
        conceptual_depth=initial.conceptual_depth,
        ontologies=(
            OntologyCandidate(
                "ontology-0",
                "identity bearer",
                "the genome is proposed as an identity bearer",
            ),
        ),
        readings=initial.readings,
    )
    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(
            FixtureClarificationPolicy(), _RefinementProvider(successor)
        )
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Что означает «определяется»?",
        target_ids=("ambiguity-0",),
    )

    policy.successor(
        interpretation=initial,
        question=question,
        answer="Гены содержат то, чем человек является на самом деле.",
    )

    entry = policy.ledger.entries[0]
    assert entry.kind is ClarificationProgressKind.StructuralResolution
    assert entry.new_item_ids == ("ontology-0",)


def test_progress_classifies_reindexed_target_by_semantic_signature():
    initial = replace(
        _space("initial", ambiguous=True),
        ambiguities=(
            Ambiguity("ambiguity-0", "term-a", "meaning-a"),
            Ambiguity("ambiguity-1", "term-b", "meaning-b"),
        ),
    )
    successor = replace(
        initial,
        id="successor",
        ambiguities=(Ambiguity("ambiguity-0", "term-b", "meaning-b"),),
    )

    class _ReturnSuccessor:
        def refine(self, interpretation, question, answer):
            return successor

    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(
            FixtureClarificationPolicy(), _ReturnSuccessor()
        )
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="What does term-a mean?",
        target_ids=("ambiguity-0",),
    )

    policy.successor(
        interpretation=initial,
        question=question,
        answer="Р“РµРЅС‹ СЃРѕРґРµСЂР¶Р°С‚ С‚Рѕ, С‡РµРј С‡РµР»РѕРІРµРє СЏРІР»СЏРµС‚СЃСЏ РЅР° СЃР°РјРѕРј РґРµР»Рµ.",
    )

    assert policy.ledger.entries[0].kind is ClarificationProgressKind.StructuralResolution
    assert policy.ledger.entries[0].new_item_ids == ()
    assert policy.ledger.entries[0].new_semantic_signatures == ()


def test_progress_allows_reindexed_distinct_target_after_previous_answer():
    initial = replace(
        _space("initial", ambiguous=True),
        ambiguities=(
            Ambiguity("ambiguity-0", "личность", "personhood or identity"),
            Ambiguity("ambiguity-1", "определяется", "cause or essence"),
        ),
    )
    successor = replace(
        initial,
        id="successor",
        ambiguities=(
            Ambiguity("ambiguity-0", "определяется", "cause or essence"),
        ),
    )
    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(
            FixtureClarificationPolicy(), _RefinementProvider(successor)
        )
    )
    first_question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Что означает «личность»?",
        target_ids=("ambiguity-0",),
    )
    policy.successor(
        interpretation=initial,
        question=first_question,
        answer="Гены содержат то, чем человек является на самом деле.",
    )

    context = type("Context", (), {"interpretation": successor, "landscape": None})
    next_question = policy.choose(context)

    assert next_question is not None
    assert next_question.id == "meaning:ambiguity-0"
    assert next_question.text == "Что именно означает «определяется» в этом вопросе?"


def test_progress_detects_new_semantics_when_ids_are_reused():
    initial = replace(
        _space("initial", ambiguous=True),
        ambiguities=(
            Ambiguity("ambiguity-0", "term-a", "meaning-a"),
            Ambiguity("ambiguity-1", "term-b", "meaning-b"),
        ),
    )
    successor = replace(
        initial,
        id="successor",
        ambiguities=(
            Ambiguity("ambiguity-0", "term-b", "meaning-b"),
            Ambiguity("ambiguity-1", "term-c", "meaning-c"),
        ),
    )

    class _ReturnSuccessor:
        def refine(self, interpretation, question, answer):
            return successor

    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(FixtureClarificationPolicy(), _ReturnSuccessor())
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="What does term-a mean?",
        target_ids=("ambiguity-0",),
    )

    policy.successor(
        interpretation=initial,
        question=question,
        answer="an answer",
    )

    entry = policy.ledger.entries[0]
    assert entry.kind is ClarificationProgressKind.StructuralResolution
    assert entry.new_item_ids == ()
    assert any("meaning-c" in signature for signature in entry.new_semantic_signatures)


@pytest.mark.parametrize(
    "successor_ambiguities",
    [
        (
            Ambiguity("ambiguity-0", "term-b", "meaning-b"),
            Ambiguity("ambiguity-1", "term-a", "meaning-a"),
        ),
        (
            Ambiguity("reindexed-0", "term-b", "meaning-b"),
            Ambiguity("reindexed-1", "term-a", "meaning-a"),
        ),
    ],
)
def test_pure_semantic_permutation_is_no_effect(successor_ambiguities):
    initial = replace(
        _space("initial", ambiguous=True),
        ambiguities=(
            Ambiguity("ambiguity-0", "term-a", "meaning-a"),
            Ambiguity("ambiguity-1", "term-b", "meaning-b"),
        ),
    )
    successor = replace(
        initial,
        id="successor",
        ambiguities=successor_ambiguities,
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="What does term-a mean?",
        target_ids=("ambiguity-0",),
    )

    progress = _classify_progress(initial, successor, question, "an answer")

    assert progress.kind is ClarificationProgressKind.NoEffect
    assert progress.new_semantic_signatures == ()


def test_reading_presupposition_reindex_preserves_semantic_identity():
    initial = replace(
        _space("initial", ambiguous=False),
        presuppositions=(
            Presupposition("presupposition-a", "entity exists"),
            Presupposition("presupposition-b", "identity is fixed"),
        ),
        readings=(
            SemanticReading(
                "reading-0",
                "identity",
                "identity reading",
                ("presupposition-a", "presupposition-b"),
            ),
        ),
    )
    successor = replace(
        initial,
        id="successor",
        presuppositions=(
            Presupposition("presupposition-1", "identity is fixed"),
            Presupposition("presupposition-0", "entity exists"),
        ),
        readings=(
            SemanticReading(
                "reading-reindexed",
                "identity",
                "identity reading",
                ("presupposition-0", "presupposition-1"),
            ),
        ),
    )
    question = ClarificationQuestion(
        id="ontology:reading-0",
        kind=ClarificationKind.Ontology,
        text="Which identity reading is intended?",
        target_ids=("reading-0",),
    )

    progress = _classify_progress(initial, successor, question, "an answer")

    assert progress.kind is ClarificationProgressKind.NoEffect


def test_structural_resolution_is_not_claimed_as_verified_resolution():
    initial = _space("initial", ambiguous=True)
    opposite = replace(
        initial,
        id="opposite",
        ambiguities=(),
        readings=(
            SemanticReading("reading-0", "opposite", "the opposite interpretation"),
        ),
    )
    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(
            FixtureClarificationPolicy(), _RefinementProvider(opposite)
        )
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Что означает «определяется»?",
        target_ids=("ambiguity-0",),
    )

    policy.successor(
        interpretation=initial,
        question=question,
        answer="Гены содержат то, чем человек является на самом деле.",
    )

    assert policy.ledger.entries[0].kind is ClarificationProgressKind.StructuralResolution
    assert policy.ledger.entries[0].kind is not ClarificationProgressKind.Resolved


def test_duplicate_target_removal_is_unverified_and_does_not_commit():
    initial = replace(
        _space("initial", ambiguous=True),
        ambiguities=(
            Ambiguity("ambiguity-a", "term", "same meaning"),
            Ambiguity("ambiguity-b", "term", "same meaning"),
        ),
    )
    successor = replace(
        initial,
        id="successor",
        ambiguities=(Ambiguity("ambiguity-a", "term", "same meaning"),),
    )

    class _ReturnSuccessor:
        def refine(self, interpretation, question, answer):
            return successor

    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(FixtureClarificationPolicy(), _ReturnSuccessor())
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-a",
        kind=ClarificationKind.Meaning,
        text="Which meaning is intended?",
        target_ids=("ambiguity-a",),
    )
    ledger_before = policy.ledger

    with pytest.raises(ValueError, match="progress=unverified"):
        policy.successor(
            interpretation=initial,
            question=question,
            answer="the answer",
        )

    assert policy.ledger is ledger_before


def test_duplicate_target_multiplicity_change_is_unverified_even_when_added():
    initial = replace(
        _space("initial", ambiguous=True),
        ambiguities=(Ambiguity("ambiguity-a", "term", "same meaning"),),
    )
    successor = replace(
        initial,
        id="successor",
        ambiguities=(
            Ambiguity("ambiguity-a", "term", "same meaning"),
            Ambiguity("ambiguity-b", "term", "same meaning"),
        ),
    )

    class _ReturnSuccessor:
        def refine(self, interpretation, question, answer):
            return successor

    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(FixtureClarificationPolicy(), _ReturnSuccessor())
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-a",
        kind=ClarificationKind.Meaning,
        text="Which meaning is intended?",
        target_ids=("ambiguity-a",),
    )

    progress = _classify_progress(initial, successor, question, "the answer")

    assert progress.kind is ClarificationProgressKind.Unverified


def test_direct_policy_successor_rejects_malformed_turn_before_commit():
    initial = _space("initial", ambiguous=True)
    successor = replace(initial, id="successor", ambiguities=())

    class _MalformedBase:
        def successor(self, *, interpretation, question, answer):
            return successor, ClarificationTurn(
                previous_interpretation_id=interpretation.id,
                question_id="wrong-question",
                answer=answer,
                successor_interpretation_id=successor.id,
            )

    policy = ProgressAwareClarificationPolicy(_MalformedBase())
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Which meaning is intended?",
        target_ids=("ambiguity-0",),
    )
    ledger_before = policy.ledger

    with pytest.raises(ValueError, match="inconsistent turn provenance"):
        policy.successor(
            interpretation=initial,
            question=question,
            answer="the answer",
        )

    assert policy.ledger is ledger_before


def test_repeated_prepared_commit_is_rejected_without_mutating_ledger():
    initial = _space("initial", ambiguous=True)
    successor = replace(initial, id="successor", ambiguities=())

    class _ReturnSuccessor:
        def refine(self, interpretation, question, answer):
            return successor

    policy = ProgressAwareClarificationPolicy(
        ModelClarificationPolicy(FixtureClarificationPolicy(), _ReturnSuccessor())
    )
    question = ClarificationQuestion(
        id="meaning:ambiguity-0",
        kind=ClarificationKind.Meaning,
        text="Which meaning is intended?",
        target_ids=("ambiguity-0",),
    )
    prepared = policy.prepare_successor(
        interpretation=initial,
        question=question,
        answer="the answer",
    )
    policy.commit_prepared(prepared)
    committed = policy.ledger

    with pytest.raises(ValueError, match="already answered"):
        policy.commit_prepared(prepared)

    assert policy.ledger is committed
