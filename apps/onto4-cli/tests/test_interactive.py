from dataclasses import dataclass

import pytest

from onto4.core import AssessmentContext, OntologyProfile, PredicateCall, PredicateExpr, PredicateSignature, Verdict
from onto4.core.evidence import AtomicVerdictStore
from onto4.pipeline import (
    ClarificationProgressKind,
    ModelClarificationPolicy,
    ProgressAwareClarificationPolicy,
    run_interactive_dialogue,
)
from onto4.providers import FormalizationRequest, InterpretationRequest
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
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
    assert result.progress.entries[0].kind is ClarificationProgressKind.Resolved


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
    assert entry.kind is ClarificationProgressKind.Resolved
    assert entry.new_item_ids == ("ontology-0",)
