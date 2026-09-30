import pytest

from onto4.core import (
    And,
    AssessmentContext,
    Equivalent,
    Implies,
    Not,
    OntologyProfile,
    Or,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    Term,
    TruthStore,
    Verdict,
    evaluate,
)


VALUES = ("T", "F", "U", "C")


def atom(name: str) -> PredicateExpr:
    return PredicateExpr(PredicateCall(name, ()))


def context() -> AssessmentContext:
    return AssessmentContext(
        ontology=OntologyProfile(
            name="operator-table",
            predicates={
                "t": PredicateSignature(()),
                "f": PredicateSignature(()),
                "u": PredicateSignature(()),
            },
            absent_concepts={"c"},
        ),
        truth=TruthStore({"t()": Verdict.T, "f()": Verdict.F, "u()": Verdict.U}),
    )


def expression_for(value: str) -> PredicateExpr:
    return atom(value.lower())


NEGATION = {"T": "F", "F": "T", "U": "U", "C": "C"}
AND = {
    "T": {"T": "T", "F": "F", "U": "U", "C": "C"},
    "F": {"T": "F", "F": "F", "U": "F", "C": "C"},
    "U": {"T": "U", "F": "F", "U": "U", "C": "C"},
    "C": {value: "C" for value in VALUES},
}
OR = {
    "T": {value: "T" if value != "C" else "C" for value in VALUES},
    "F": {"T": "T", "F": "F", "U": "U", "C": "C"},
    "U": {"T": "T", "F": "U", "U": "U", "C": "C"},
    "C": {value: "C" for value in VALUES},
}
IMPLIES = {
    "T": {"T": "T", "F": "F", "U": "U", "C": "C"},
    "F": {value: "T" if value != "C" else "C" for value in VALUES},
    "U": {"T": "T", "F": "U", "U": "U", "C": "C"},
    "C": {value: "C" for value in VALUES},
}
EQUIVALENT = {
    "T": {"T": "T", "F": "F", "U": "U", "C": "C"},
    "F": {"T": "F", "F": "T", "U": "U", "C": "C"},
    "U": {value: "U" if value != "C" else "C" for value in VALUES},
    "C": {value: "C" for value in VALUES},
}


@pytest.mark.parametrize("value, expected", NEGATION.items())
def test_negation_table(value, expected):
    result = evaluate(Not(expression_for(value)), context())
    assert result.verdict is Verdict(expected)


@pytest.mark.parametrize("left", VALUES)
@pytest.mark.parametrize("right", VALUES)
@pytest.mark.parametrize(
    "operator, table, constructor",
    [
        ("and", AND, And),
        ("or", OR, Or),
        ("implies", IMPLIES, Implies),
        ("equivalent", EQUIVALENT, Equivalent),
    ],
)
def test_binary_operator_tables(left, right, operator, table, constructor):
    result = evaluate(constructor(expression_for(left), expression_for(right)), context())
    assert result.verdict is Verdict(table[left][right]), f"{operator}: {left} {right}"
