import pytest

from onto4.core import AssessmentContext, OntologyProfile, PredicateSignature
from onto4.providers import (
    AssessmentContextProjection,
    FormalizationRequest,
    InterpretationRequest,
    project_assessment_context,
)
from onto4.reasoning import ConceptualDepth, InterpretationSpace, SemanticReading


def test_context_projection_contains_ontology_affordances_only():
    context = AssessmentContext(
        ontology=OntologyProfile(
            name="physical_objects",
            types={"car_A": "PhysicalObject", "integer_7": "Integer"},
            predicates={"has_mass": PredicateSignature(("PhysicalObject",))},
            type_parents={"PhysicalObject": ("Entity",)},
        )
    )

    projection = project_assessment_context("physical_objects", context)
    data = projection.as_dict()

    assert data["id"] == "physical_objects"
    assert data["ontology"] == "physical_objects"
    assert data["symbols"] == [
        {"name": "car_A", "type": "PhysicalObject"},
        {"name": "integer_7", "type": "Integer"},
    ]
    assert data["predicates"] == [
        {"name": "has_mass", "domain": ["PhysicalObject"], "returns": "Proposition"}
    ]
    assert "evidence" not in data
    assert "verdicts" not in data


def test_formalization_request_rejects_projection_from_another_context():
    space = InterpretationSpace(
        id="space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(SemanticReading("reading-0", "closed", "not open"),),
    )
    projection = AssessmentContextProjection("physical_objects", "physical_objects")

    with pytest.raises(ValueError, match="projection ID"):
        FormalizationRequest(
            space,
            reading=space.readings[0],
            context_id="other_context",
            context_projection=projection,
        )
