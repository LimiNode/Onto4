from onto4.core import PredicateCall, PredicateExpr
from onto4.providers import (
    FixtureFormalizationProvider,
    FixtureInterpretationProvider,
    FormalizationRequest,
    InterpretationRequest,
)
from onto4.reasoning import ConceptualDepth, FormalizationCandidate, InterpretationSpace


def test_fixture_providers_preserve_interpretation_to_candidate_boundary():
    source = "What persists through change?"
    space = InterpretationSpace(
        source_text=source,
        conceptual_depth=ConceptualDepth.Philosophical,
    )
    candidate = FormalizationCandidate(
        id="continuity",
        label="continuity reading",
        formalization_id="continuity",
        context_id="process",
        formalization=PredicateExpr(PredicateCall("continuity", ())),
        reading_id="continuity",
    )

    interpretation_provider = FixtureInterpretationProvider({source: space})
    formalization_provider = FixtureFormalizationProvider({source: (candidate,)})

    interpreted = interpretation_provider.interpret(InterpretationRequest(source))
    candidates = formalization_provider.formalize(FormalizationRequest(interpreted))

    assert interpreted is space
    assert candidates == (candidate,)
    assert not hasattr(interpreted, "verdict")


def test_fixture_providers_fail_closed_for_unknown_source():
    provider = FixtureInterpretationProvider({})

    try:
        provider.interpret(InterpretationRequest("missing"))
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("unknown source must not produce an interpretation")
