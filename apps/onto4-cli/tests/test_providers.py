from onto4.core import PredicateCall, PredicateExpr
from onto4.providers import (
    FixtureFormalizationProvider,
    FixtureInterpretationProvider,
    FormalizationRequest,
    InterpretationRequest,
)
from onto4.reasoning import (
    ConceptualDepth,
    FormalizationCandidate,
    InterpretationSpace,
    SemanticReading,
)


def test_fixture_providers_preserve_interpretation_to_candidate_boundary():
    source = "What persists through change?"
    space = InterpretationSpace(
        id="continuity-space",
        source_text=source,
        conceptual_depth=ConceptualDepth.Philosophical,
        readings=(SemanticReading("continuity", "continuity", "continuous identity"),),
    )
    candidate = FormalizationCandidate(
        id="continuity",
        label="continuity reading",
        formalization_id="continuity",
        context_id="process",
        formalization=PredicateExpr(PredicateCall("continuity", ())),
        reading_id="continuity",
    )

    interpretation_provider = FixtureInterpretationProvider(
        {(source, ConceptualDepth.Philosophical): space}
    )
    formalization_provider = FixtureFormalizationProvider({space.id: (candidate,)})

    interpreted = interpretation_provider.interpret(
        InterpretationRequest(source, conceptual_depth=ConceptualDepth.Philosophical)
    )
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


def test_interpretation_fixture_routes_same_text_by_depth():
    source = "Am I the same person?"
    ordinary = InterpretationSpace(
        id="ordinary-space",
        source_text=source,
        conceptual_depth=ConceptualDepth.Ordinary,
    )
    ontology_sensitive = InterpretationSpace(
        id="ontology-sensitive-space",
        source_text=source,
        conceptual_depth=ConceptualDepth.OntologySensitive,
    )
    provider = FixtureInterpretationProvider(
        {
            (source, ConceptualDepth.Ordinary): ordinary,
            (source, ConceptualDepth.OntologySensitive): ontology_sensitive,
        }
    )

    assert provider.interpret(
        InterpretationRequest(source, conceptual_depth=ConceptualDepth.Ordinary)
    ) is ordinary
    assert provider.interpret(
        InterpretationRequest(source, conceptual_depth=ConceptualDepth.OntologySensitive)
    ) is ontology_sensitive


def test_formalization_fixture_is_keyed_by_interpretation_identity():
    source = "Am I the same person?"
    ordinary = InterpretationSpace(
        id="ordinary-reading-space",
        source_text=source,
        conceptual_depth=ConceptualDepth.Ordinary,
    )
    ontology_sensitive = InterpretationSpace(
        id="ontology-sensitive-space",
        source_text=source,
        conceptual_depth=ConceptualDepth.OntologySensitive,
    )
    ordinary_candidate = FormalizationCandidate(
        id="continuity",
        label="continuity",
        formalization_id="continuity",
        context_id="process",
        formalization=None,
    )
    ontology_candidate = FormalizationCandidate(
        id="substance",
        label="substance",
        formalization_id="substance",
        context_id="substance",
        formalization=None,
    )
    provider = FixtureFormalizationProvider(
        {
            ordinary.id: (ordinary_candidate,),
            ontology_sensitive.id: (ontology_candidate,),
        }
    )

    assert provider.formalize(FormalizationRequest(ordinary)) == (ordinary_candidate,)
    assert provider.formalize(FormalizationRequest(ontology_sensitive)) == (ontology_candidate,)


def test_formalization_fixture_rejects_unknown_reading_provenance():
    space = InterpretationSpace(
        id="space",
        source_text="Question",
        conceptual_depth=ConceptualDepth.Reflective,
    )
    candidate = FormalizationCandidate(
        id="candidate",
        label="candidate",
        formalization_id="formalization",
        context_id="context",
        formalization=None,
        reading_id="missing-reading",
    )
    provider = FixtureFormalizationProvider({space.id: (candidate,)})

    try:
        provider.formalize(FormalizationRequest(space))
    except ValueError as exc:
        assert "missing-reading" in str(exc)
    else:
        raise AssertionError("unknown reading provenance must fail closed")
