from pathlib import Path

from onto4.core import (
    AssessmentContext,
    AtomicVerdictStore,
    OntologyProfile,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    Term,
    Verdict,
    evaluate,
)
from onto4.pipeline import load_clarification_corpus


ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "eval/clarification/philosophical-dialogues-v2.yaml"


def _context(*, types, predicates, verdicts=()):
    return AssessmentContext(
        ontology=OntologyProfile(
            name="fixture",
            types=dict(types),
            predicates=dict(predicates),
        ),
        verdicts=AtomicVerdictStore(dict(verdicts)),
    )


def test_v2_corpus_has_context_scoped_and_dialogue_cases_without_oracle_leakage():
    corpus = load_clarification_corpus(CORPUS)

    assert corpus.version == 2
    assert corpus.name == "philosophical-dialogues-v2"
    assert len(corpus.cases) >= 46
    assert len({case.case_id for case in corpus.cases}) == len(corpus.cases)
    assert len(corpus.context_profiles) >= 16
    assert sum(case.mode == "dialogue" for case in corpus.cases) >= 12
    assert all(case.context in corpus.context_profiles for case in corpus.cases)
    for case in corpus.cases:
        public = case.public_input()
        assert set(public) == {"utterance"}
        assert "hidden_interpretation" not in public
        assert "expected_clarification" not in public
        assert "expected_after_answer" not in public
        assert "dialogue" not in public


def test_v2_dialogues_have_structured_turns_and_none_of_the_above_case():
    corpus = load_clarification_corpus(CORPUS)
    dialogues = [case for case in corpus.cases if case.mode == "dialogue"]

    assert all(len(case.dialogue) >= 2 for case in dialogues)
    assert all(
        len({turn["turn_id"] for turn in case.dialogue}) == len(case.dialogue)
        for case in dialogues
    )
    assert any(
        any("Ни один вариант" in turn["text"] for turn in case.dialogue)
        for case in dialogues
    )


def test_deterministic_gold_fixtures_cover_t_f_u_and_c_without_llm():
    integer_predicate = PredicateSignature(("Integer", "Integer"))
    arithmetic = _context(
        types={"two": "Integer", "one": "Integer", "seven": "Integer"},
        predicates={"greater": integer_predicate},
        verdicts={"greater(two, one)": Verdict.T, "greater(two, seven)": Verdict.F},
    )
    assert evaluate(
        PredicateExpr(PredicateCall("greater", (Term("two"), Term("one")))),
        arithmetic,
    ).verdict is Verdict.T
    assert evaluate(
        PredicateExpr(PredicateCall("greater", (Term("two"), Term("seven")))),
        arithmetic,
    ).verdict is Verdict.F

    unknown = _context(
        types={"teapot": "PhysicalObject"},
        predicates={"exists": PredicateSignature(("PhysicalObject",))},
    )
    assert evaluate(
        PredicateExpr(PredicateCall("exists", (Term("teapot"),))), unknown
    ).verdict is Verdict.U

    category = _context(
        types={"seven": "Number"},
        predicates={"sleeps": PredicateSignature(("Person",))},
    )
    assert evaluate(
        PredicateExpr(PredicateCall("sleeps", (Term("seven"),))), category
    ).verdict is Verdict.C
