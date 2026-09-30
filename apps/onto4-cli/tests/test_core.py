from onto4.core import (
    And,
    AssessmentContext,
    AssessmentState,
    Evidence4,
    OntologyProfile,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    SemanticStatus,
    UnsupportedProfile,
    Term,
    Verdict,
    Or,
    evaluate,
)


def context_for(*, predicates, types, absent=(), evidence=None, verdicts=None, semantics=None, inference=None):
    from onto4.core.context import InferenceProfile, SemanticProfile
    from onto4.core.evidence import AtomicVerdictStore, EvidenceStore

    return AssessmentContext(
        ontology=OntologyProfile(
            name="test",
            types=types,
            predicates=predicates,
            absent_concepts=set(absent),
        ),
        evidence=EvidenceStore(evidence or {}),
        verdicts=AtomicVerdictStore(verdicts or {}),
        semantics=semantics or SemanticProfile(),
        inference=inference or InferenceProfile(),
    )


def atom(name, *args):
    return PredicateExpr(PredicateCall(name, tuple(Term(arg) for arg in args)))


def test_has_mass_of_integer_is_category_error():
    context = context_for(
        types={"integer_7": "Integer"},
        predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
    )

    result = evaluate(atom("has_mass", "integer_7"), context)

    assert result.semantic_status is SemanticStatus.Inapplicable
    assert result.verdict is Verdict.C
    assert any(item.code == "type_mismatch" for item in result.diagnostics)


def test_has_mass_of_car_without_evidence_is_unresolved():
    context = context_for(
        types={"car_A": "PhysicalObject"},
        predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
    )

    result = evaluate(atom("has_mass", "car_A"), context)

    assert result.semantic_status is SemanticStatus.Admitted
    assert result.verdict is Verdict.U
    assert result.evidence is Evidence4.Neither


def test_established_truth_is_separate_from_evidence():
    predicate = PredicateSignature(("PhysicalObject",))
    base = {"car_A": "PhysicalObject"}
    true_context = context_for(
        types=base,
        predicates={"has_mass": predicate},
        verdicts={"has_mass(car_A)": Verdict.T},
        evidence={"has_mass(car_A)": Evidence4.TrueOnly},
    )
    false_context = context_for(
        types=base,
        predicates={"has_mass": predicate},
        verdicts={"has_mass(car_A)": Verdict.F},
        evidence={"has_mass(car_A)": Evidence4.FalseOnly},
    )

    assert evaluate(atom("has_mass", "car_A"), true_context).verdict is Verdict.T
    assert evaluate(atom("has_mass", "car_A"), false_context).verdict is Verdict.F


def test_supporting_evidence_alone_does_not_establish_truth():
    context = context_for(
        types={"car_A": "PhysicalObject"},
        predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
        evidence={"has_mass(car_A)": Evidence4.TrueOnly},
    )

    result = evaluate(atom("has_mass", "car_A"), context)

    assert result.verdict is Verdict.U
    assert result.evidence is Evidence4.TrueOnly


def test_strict_formula_does_not_hide_category_error():
    context = context_for(
        types={"car_A": "PhysicalObject", "integer_7": "Integer"},
        predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
        verdicts={"has_mass(car_A)": Verdict.T},
        evidence={"has_mass(car_A)": Evidence4.TrueOnly},
    )
    expression = And(atom("has_mass", "car_A"), atom("has_mass", "integer_7"))

    result = evaluate(expression, context)

    assert result.verdict is Verdict.C


def test_strict_or_does_not_hide_category_error():
    context = context_for(
        types={"car_A": "PhysicalObject", "integer_7": "Integer"},
        predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
        verdicts={"has_mass(car_A)": Verdict.T},
        evidence={"has_mass(car_A)": Evidence4.TrueOnly},
    )

    result = evaluate(Or(atom("has_mass", "car_A"), atom("has_mass", "integer_7")), context)

    assert result.verdict is Verdict.C


def test_missing_formalization_has_no_onto4_verdict():
    result = evaluate(None, AssessmentContext())

    assert result.state is AssessmentState.FormalizationUnresolved
    assert result.semantic_status is None
    assert result.verdict is None


def test_unknown_reference_is_not_category_error():
    context = context_for(
        types={},
        predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
    )

    result = evaluate(atom("has_mass", "unknown_car"), context)

    assert result.state is AssessmentState.FormalizationUnresolved
    assert result.semantic_status is None
    assert result.verdict is None


def test_unknown_predicate_is_unresolved_until_explicitly_absent():
    context = context_for(types={"car_A": "PhysicalObject"}, predicates={})

    result = evaluate(atom("has_mass", "car_A"), context)

    assert result.state is AssessmentState.FormalizationUnresolved
    assert result.verdict is None


def test_explicitly_absent_predicate_is_category_error():
    context = context_for(
        types={"car_A": "PhysicalObject"},
        predicates={},
        absent={"has_mass"},
    )

    result = evaluate(atom("has_mass", "car_A"), context)

    assert result.state is AssessmentState.Assessed
    assert result.semantic_status is SemanticStatus.Inapplicable
    assert result.verdict is Verdict.C


def test_category_error_is_decisive_with_unresolved_sibling():
    context = context_for(
        types={"integer_7": "Integer"},
        predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
    )
    expression = And(
        atom("has_mass", "integer_7"),
        atom("has_mass", "unknown_car"),
    )

    result = evaluate(expression, context)

    assert result.state is AssessmentState.Assessed
    assert result.semantic_status is SemanticStatus.Inapplicable
    assert result.verdict is Verdict.C
    assert {item.code for item in result.diagnostics} == {"type_mismatch", "unknown_symbol"}


def test_compound_evidence_is_uncomputed_unless_explicitly_supplied():
    expression = And(atom("a"), atom("b"))
    context = context_for(
        types={},
        predicates={"a": PredicateSignature(()), "b": PredicateSignature(())},
        verdicts={"a()": Verdict.T, "b()": Verdict.T},
        evidence={"a()": Evidence4.TrueOnly, "b()": Evidence4.TrueOnly},
    )

    result = evaluate(expression, context)

    assert result.verdict is Verdict.T
    assert result.evidence is None

    context.evidence.entries["and(a(), b())"] = Evidence4.TrueOnly
    explicit = evaluate(expression, context)
    assert explicit.evidence is Evidence4.TrueOnly


def test_unsupported_expression_is_an_invalid_request():
    result = evaluate(object(), AssessmentContext())  # type: ignore[arg-type]

    assert result.state is AssessmentState.InvalidRequest
    assert result.semantic_status is None
    assert result.verdict is None


def test_unsupported_profiles_fail_closed():
    from onto4.core.context import InferenceProfile, SemanticProfile

    context = context_for(
        types={},
        predicates={"a": PredicateSignature(())},
        verdicts={"a()": Verdict.T},
        semantics=SemanticProfile(name="non_strict", strict=False),
    )
    try:
        evaluate(atom("a"), context)
    except UnsupportedProfile:
        pass
    else:
        raise AssertionError("unsupported semantic profile was silently accepted")

    context.inference = InferenceProfile(name="solver")
    try:
        evaluate(atom("a"), context)
    except UnsupportedProfile:
        pass
    else:
        raise AssertionError("unsupported inference profile was silently accepted")


def test_arity_and_non_propositional_use_are_category_errors():
    arity_context = context_for(
        types={"car_A": "PhysicalObject"},
        predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
    )
    arity_result = evaluate(atom("has_mass"), arity_context)
    assert arity_result.verdict is Verdict.C
    assert any(item.code == "arity_mismatch" for item in arity_result.diagnostics)

    function_context = context_for(
        types={"car_A": "PhysicalObject"},
        predicates={"mass": PredicateSignature(("PhysicalObject",), returns="MassValue")},
    )
    function_result = evaluate(atom("mass", "car_A"), function_context)
    assert function_result.verdict is Verdict.C
    assert any(item.code == "non_propositional_predicate" for item in function_result.diagnostics)
