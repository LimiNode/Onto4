from onto4.core import (
    AssessmentContext,
    OntologyProfile,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    Term,
    Verdict,
)
from onto4.core.evidence import AtomicVerdictStore
from onto4.pipeline import ask
from onto4.providers import (
    FixtureFormalizationProvider,
    FixtureInterpretationProvider,
    FormalizationRequest,
    InterpretationRequest,
)
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationContext,
    ClarificationState,
    ConceptualDepth,
    CrossCandidateStatus,
    AssessmentLandscape,
    FixtureClarificationPolicy,
    FormalizationCandidate,
    InterpretationSpace,
    PipelineDisposition,
    SemanticReading,
)


def atom(name: str) -> PredicateExpr:
    return PredicateExpr(PredicateCall(name, ()))


def context(*, verdicts=None, predicates=("a", "b")) -> AssessmentContext:
    return AssessmentContext(
        ontology=OntologyProfile(
            name="fixture",
            predicates={name: PredicateSignature(()) for name in predicates},
        ),
        verdicts=AtomicVerdictStore(verdicts or {}),
    )


def run(space, candidates, contexts, *, source="question"):
    interpretation_provider = FixtureInterpretationProvider(
        {(source, space.conceptual_depth): space}
    )
    formalization_provider = FixtureFormalizationProvider({space.id: tuple(candidates)})
    return ask(
        InterpretationRequest(source, conceptual_depth=space.conceptual_depth),
        interpretation_provider=interpretation_provider,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=FixtureClarificationPolicy(),
    )


def candidate(identifier, formalization_id, context_id, expression, *, reading_id=None):
    return FormalizationCandidate(
        id=identifier,
        label=identifier,
        formalization_id=formalization_id,
        context_id=context_id,
        formalization=expression,
        reading_id=reading_id,
    )


def space(*, identifier="space", ambiguities=(), readings=()):
    return InterpretationSpace(
        id=identifier,
        source_text="question",
        conceptual_depth=ConceptualDepth.Philosophical,
        ambiguities=ambiguities,
        readings=readings,
    )


def test_unambiguous_assessed_candidate_is_complete():
    result = run(
        space(),
        [candidate("a", "formal-a", "fixture", atom("a"))],
        {"fixture": context(verdicts={"a()": Verdict.T})},
    )

    assert result.disposition is PipelineDisposition.Complete
    assert result.clarification_question is None
    assert result.assessments[0].result.verdict is Verdict.T


def test_material_ambiguity_requests_meaning_clarification():
    result = run(
        space(ambiguities=(Ambiguity("identity-term", "тот же", "критерий тождества"),)),
        [candidate("a", "formal-a", "fixture", atom("a"))],
        {"fixture": context(verdicts={"a()": Verdict.T})},
    )

    assert result.disposition is PipelineDisposition.AskClarification
    assert result.clarification_question.kind is ClarificationKind.Meaning
    assert result.clarification_question.target_ids == ("identity-term",)


def test_context_dependence_requests_context_clarification():
    result = run(
        space(),
        [
            candidate("present", "same", "present", atom("a")),
            candidate("eternal", "same", "eternal", atom("a")),
        ],
        {
            "present": context(verdicts={"a()": Verdict.T}),
            "eternal": context(verdicts={"a()": Verdict.F}),
        },
    )

    assert result.disposition is PipelineDisposition.AskClarification
    assert result.clarification_question.kind is ClarificationKind.Context
    assert result.clarification_question.choices == ("present", "eternal")


def test_formalization_conflict_requests_reading_clarification():
    readings = (
        SemanticReading("continuity", "continuity", "process identity"),
        SemanticReading("substance", "substance", "persistent identity"),
    )
    result = run(
        space(readings=readings),
        [
            candidate("continuity", "continuity", "fixture", atom("a"), reading_id="continuity"),
            candidate("substance", "substance", "fixture", atom("b"), reading_id="substance"),
        ],
        {"fixture": context(verdicts={"a()": Verdict.T, "b()": Verdict.F})},
    )

    assert result.disposition is PipelineDisposition.AskClarification
    assert result.clarification_question.kind is ClarificationKind.Meaning
    assert result.clarification_question.target_ids == ("continuity", "substance")


def test_mixed_dependence_preserves_both_axes_in_question_targets():
    result = run(
        space(),
        [
            candidate("present", "present-formal", "present", atom("a")),
            candidate("eternal", "eternal-formal", "eternal", atom("a")),
        ],
        {
            "present": context(verdicts={"a()": Verdict.T}),
            "eternal": context(verdicts={"a()": Verdict.F}),
        },
    )

    assert result.disposition is PipelineDisposition.AskClarification
    assert result.clarification_question.kind is ClarificationKind.Formalization
    assert result.clarification_question.text == "Какой вариант формализации следует рассматривать?"
    assert result.clarification_question.target_ids == ("present", "eternal")


def test_mixed_dependence_uses_reading_ids_for_meaning_question():
    readings = (
        SemanticReading("continuity", "continuity", "process identity"),
        SemanticReading("substance", "substance", "persistent identity"),
    )
    result = run(
        space(readings=readings),
        [
            candidate(
                "present",
                "present-formal",
                "present",
                atom("a"),
                reading_id="continuity",
            ),
            candidate(
                "eternal",
                "eternal-formal",
                "eternal",
                atom("a"),
                reading_id="substance",
            ),
        ],
        {
            "present": context(verdicts={"a()": Verdict.T}),
            "eternal": context(verdicts={"a()": Verdict.F}),
        },
    )

    assert result.clarification_question.kind is ClarificationKind.Meaning
    assert result.clarification_question.target_ids == ("continuity", "substance")
    assert result.clarification_question.choices == ("continuity", "substance")


def test_unresolved_formalization_requests_formalization_clarification():
    result = run(
        space(),
        [candidate("missing", "missing", "fixture", None)],
        {"fixture": context()},
    )

    assert result.disposition is PipelineDisposition.AskClarification
    assert result.clarification_question.kind is ClarificationKind.Formalization
    assert result.clarification_question.text == (
        "Что нужно уточнить, чтобы завершить формализацию этого чтения?"
    )


def test_unknown_symbol_unresolved_requests_reference_clarification():
    reference_context = AssessmentContext(
        ontology=OntologyProfile(
            name="fixture",
            types={},
            predicates={"knows": PredicateSignature(("Person",))},
        ),
        verdicts=AtomicVerdictStore(),
    )
    result = run(
        space(),
        [
            candidate(
                "reference",
                "reference-formal",
                "fixture",
                PredicateExpr(PredicateCall("knows", (Term("missing"),))),
            )
        ],
        {"fixture": reference_context},
    )

    assert result.disposition is PipelineDisposition.AskClarification
    assert result.clarification_question.kind is ClarificationKind.Reference
    assert result.clarification_question.text == "Какой объект или референс имеется в виду?"


def test_admitted_unknown_verdict_requests_evidence():
    result = run(
        space(),
        [candidate("a", "formal-a", "fixture", atom("a"))],
        {"fixture": context()},
    )

    assert result.disposition is PipelineDisposition.NeedEvidence
    assert result.clarification_question is None
    assert result.assessments[0].result.verdict is Verdict.U


def test_category_mismatch_is_complete_with_c_not_evidence_request():
    mismatch_context = AssessmentContext(
        ontology=OntologyProfile(
            name="fixture",
            predicates={"a": PredicateSignature(("PhysicalObject",))},
        ),
        verdicts=AtomicVerdictStore(),
    )
    result = run(
        space(),
        [candidate("a", "formal-a", "fixture", atom("a"))],
        {"fixture": mismatch_context},
    )

    assert result.disposition is PipelineDisposition.Complete
    assert result.assessments[0].result.verdict is Verdict.C


def test_invalid_request_cannot_proceed():
    result = run(
        space(),
        [candidate("invalid", "invalid", "fixture", object())],
        {"fixture": context()},
    )

    assert result.disposition is PipelineDisposition.CannotProceed
    assert result.landscape.invalid_candidate_ids == ("invalid",)


def test_fixture_transition_preserves_clarification_provenance():
    initial = space(identifier="initial")
    successor = space(identifier="successor")
    question = FixtureClarificationPolicy().choose(
        ClarificationContext(
            interpretation=initial,
            candidates=(),
            assessments=(),
            landscape=AssessmentLandscape((), CrossCandidateStatus.FormalizationUnresolved),
        )
    )
    policy = FixtureClarificationPolicy(
        transitions={(initial.id, question.id, "the reference"): successor}
    )

    next_space, turn = policy.successor(
        interpretation=initial,
        question=question,
        answer="the reference",
    )
    state = ClarificationState().record(
        previous_interpretation_id=turn.previous_interpretation_id,
        question_id=turn.question_id,
        answer=turn.answer,
        successor_interpretation_id=turn.successor_interpretation_id,
    )

    assert next_space is successor
    assert state.turns[0] == turn


def test_clarification_state_rejects_discontinuous_history():
    state = ClarificationState().record(
        previous_interpretation_id="initial",
        question_id="q1",
        answer="answer",
        successor_interpretation_id="successor",
    )

    try:
        state.record(
            previous_interpretation_id="unrelated",
            question_id="q2",
            answer="answer",
            successor_interpretation_id="next",
        )
    except ValueError as exc:
        assert "discontinuous" in str(exc)
    else:
        raise AssertionError("discontinuous clarification history must fail closed")
