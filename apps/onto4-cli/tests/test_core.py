from onto4.core import (
    And,
    AssessmentContext,
    Evidence4,
    OntologyProfile,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    SemanticStatus,
    Term,
    Verdict,
    Or,
    evaluate,
)


def context_for(*, predicates, types, absent=(), evidence=None):
    from onto4.core.evidence import EvidenceStore

    return AssessmentContext(
        ontology=OntologyProfile(
            name="test",
            types=types,
            predicates=predicates,
            absent_concepts=set(absent),
        ),
        evidence=EvidenceStore(evidence or {}),
    )


def atom(name, *args):
    return PredicateExpr(PredicateCall(name, tuple(Term(arg) for arg in args)))


def test_mass_of_integer_is_category_error():
    context = context_for(
        types={"integer_7": "Integer"},
        predicates={"mass": PredicateSignature(("PhysicalObject",))},
    )

    result = evaluate(atom("mass", "integer_7"), context)

    assert result.semantic_status is SemanticStatus.Inapplicable
    assert result.verdict is Verdict.C
    assert any(item.code == "type_mismatch" for item in result.diagnostics)


def test_mass_of_car_without_evidence_is_unresolved():
    context = context_for(
        types={"car_A": "PhysicalObject"},
        predicates={"mass": PredicateSignature(("PhysicalObject",))},
    )

    result = evaluate(atom("mass", "car_A"), context)

    assert result.semantic_status is SemanticStatus.Admitted
    assert result.verdict is Verdict.U
    assert result.evidence is Evidence4.Neither


def test_evidence_can_establish_true_and_false():
    predicate = PredicateSignature(("PhysicalObject",))
    base = {"car_A": "PhysicalObject"}
    true_context = context_for(
        types=base,
        predicates={"mass": predicate},
        evidence={"mass(car_A)": Evidence4.TrueOnly},
    )
    false_context = context_for(
        types=base,
        predicates={"mass": predicate},
        evidence={"mass(car_A)": Evidence4.FalseOnly},
    )

    assert evaluate(atom("mass", "car_A"), true_context).verdict is Verdict.T
    assert evaluate(atom("mass", "car_A"), false_context).verdict is Verdict.F


def test_strict_formula_does_not_hide_category_error():
    context = context_for(
        types={"car_A": "PhysicalObject", "integer_7": "Integer"},
        predicates={"mass": PredicateSignature(("PhysicalObject",))},
        evidence={"mass(car_A)": Evidence4.TrueOnly},
    )
    expression = And(atom("mass", "car_A"), atom("mass", "integer_7"))

    result = evaluate(expression, context)

    assert result.verdict is Verdict.C


def test_strict_or_does_not_hide_category_error():
    context = context_for(
        types={"car_A": "PhysicalObject", "integer_7": "Integer"},
        predicates={"mass": PredicateSignature(("PhysicalObject",))},
        evidence={"mass(car_A)": Evidence4.TrueOnly},
    )

    result = evaluate(Or(atom("mass", "car_A"), atom("mass", "integer_7")), context)

    assert result.verdict is Verdict.C


def test_missing_formalization_has_no_onto4_verdict():
    result = evaluate(None, AssessmentContext())

    assert result.semantic_status is SemanticStatus.Unresolved
    assert result.verdict is None
