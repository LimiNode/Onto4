import json

import pytest

from onto4.core import PredicateExpr
from onto4.providers import (
    FormalizationRequest,
    InterpretationRequest,
    OpenAICompatibleFormalizationProvider,
    OpenAICompatibleInterpretationProvider,
    ProviderSchemaError,
)
from onto4.reasoning import (
    Ambiguity,
    ConceptualDepth,
    InterpretationSpace,
    OntologyCandidate,
    Presupposition,
    SemanticReading,
)


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    def complete(self, messages, **kwargs):
        self.messages = messages
        return {"choices": [{"message": {"content": json.dumps(self.payload)}}]}


def interpretation_payload(source_text="The door is closed."):
    return {
        "id": "door-space",
        "source_text": source_text,
        "conceptual_depth": "ordinary",
        "ambiguities": [
            {"id": "closed", "term": "closed", "description": "position or lock"}
        ],
        "presuppositions": [],
        "ontologies": [],
        "readings": [
            {
                "id": "closed-position",
                "label": "closed position",
                "description": "the door leaf is not open",
                "presupposition_ids": [],
            }
        ],
    }


def test_interpretation_adapter_parses_structured_space_and_requests_json_mode():
    client = FakeClient(interpretation_payload())
    provider = OpenAICompatibleInterpretationProvider(client)

    result = provider.interpret(InterpretationRequest("The door is closed."))

    assert result.id == "door-space"
    assert result.conceptual_depth is ConceptualDepth.Ordinary
    assert result.readings[0].id == "closed-position"
    assert client.messages[0]["role"] == "system"


def test_interpretation_adapter_preserves_explicit_requested_depth():
    client = FakeClient(interpretation_payload())

    result = OpenAICompatibleInterpretationProvider(client).interpret(
        InterpretationRequest(
            "The door is closed.", conceptual_depth=ConceptualDepth.Ordinary
        )
    )

    assert result.conceptual_depth is ConceptualDepth.Ordinary
    assert "requested_conceptual_depth: ordinary" in client.messages[1]["content"]
    assert "Preserve this requested conceptual_depth exactly" in client.messages[1]["content"]


def test_interpretation_adapter_allows_model_depth_selection_when_unspecified():
    client = FakeClient(interpretation_payload())

    OpenAICompatibleInterpretationProvider(client).interpret(
        InterpretationRequest("The door is closed.")
    )

    prompt = client.messages[1]["content"]
    assert "requested_conceptual_depth: auto" in prompt
    assert "Select one supported ConceptualDepth" in prompt
    assert "requested_conceptual_depth: ordinary" not in prompt


def test_interpretation_adapter_rejects_explicit_depth_mismatch():
    client = FakeClient(interpretation_payload())

    with pytest.raises(ProviderSchemaError, match="conceptual_depth"):
        OpenAICompatibleInterpretationProvider(client).interpret(
            InterpretationRequest(
                "The door is closed.", conceptual_depth=ConceptualDepth.Philosophical
            )
        )


def test_interpretation_adapter_rejects_source_text_rebinding():
    client = FakeClient(interpretation_payload("Other text"))

    with pytest.raises(ProviderSchemaError, match="source_text"):
        OpenAICompatibleInterpretationProvider(client).interpret(
            InterpretationRequest("The door is closed.")
        )


def test_interpretation_adapter_rejects_unknown_fields():
    payload = interpretation_payload()
    payload["unexpected"] = True

    with pytest.raises(ProviderSchemaError, match="unknown fields"):
        OpenAICompatibleInterpretationProvider(FakeClient(payload)).interpret(
            InterpretationRequest("The door is closed.")
        )


def test_interpretation_adapter_rejects_non_json_model_content():
    class InvalidClient:
        def complete(self, messages, **kwargs):
            return {"choices": [{"message": {"content": "not-json"}}]}

    with pytest.raises(ProviderSchemaError, match="valid JSON"):
        OpenAICompatibleInterpretationProvider(InvalidClient()).interpret(
            InterpretationRequest("The door is closed.")
        )


def test_formalization_adapter_parses_predicate_candidate():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(SemanticReading("closed-position", "closed", "not open"),),
    )
    payload = {
        "candidates": [
            {
                "id": "position",
                "label": "closed position",
                "formalization_id": "closed-position",
                "context_id": "door-context",
                "reading_id": "closed-position",
                "assumptions": [],
                "formalization": {
                    "kind": "predicate",
                    "name": "ClosedPosition",
                    "args": [{"name": "door", "declared_type": "Door"}],
                },
            }
        ]
    }

    candidates = OpenAICompatibleFormalizationProvider(FakeClient(payload)).formalize(
        FormalizationRequest(space)
    )

    assert len(candidates) == 1
    assert isinstance(candidates[0].formalization, PredicateExpr)
    assert candidates[0].reading_id == "closed-position"


def test_formalization_prompt_exposes_complete_interpretation_provenance():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        ambiguities=(Ambiguity("closed", "closed", "position or lock"),),
        presuppositions=(Presupposition("door-present", "a door is present"),),
        ontologies=(OntologyCandidate("physical-door", "physical door", "a door object"),),
        readings=(
            SemanticReading(
                "closed-position",
                "closed position",
                "the leaf is not open",
                ("door-present",),
            ),
        ),
    )
    client = FakeClient({"candidates": []})

    OpenAICompatibleFormalizationProvider(client).formalize(FormalizationRequest(space))

    prompt = client.messages[1]["content"]
    assert '"closed-position"' in prompt
    assert '"door-present"' in prompt
    assert "position or lock" in prompt
    assert "Use only the supplied reading IDs" in prompt


def test_formalization_adapter_rejects_unknown_reading_provenance():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
    )
    payload = {
        "candidates": [
            {
                "id": "position",
                "label": "closed position",
                "formalization_id": "closed-position",
                "context_id": "door-context",
                "reading_id": "missing",
                "formalization": None,
            }
        ]
    }

    with pytest.raises(ProviderSchemaError, match="unknown interpretation reading"):
        OpenAICompatibleFormalizationProvider(FakeClient(payload)).formalize(
            FormalizationRequest(space)
        )


def test_formalization_adapter_requires_reading_provenance_when_readings_exist():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(SemanticReading("closed-position", "closed", "not open"),),
    )
    payload = {
        "candidates": [
            {
                "id": "position",
                "label": "closed position",
                "formalization_id": "closed-position",
                "context_id": "door-context",
                "formalization": None,
            }
        ]
    }

    with pytest.raises(ProviderSchemaError, match="required"):
        OpenAICompatibleFormalizationProvider(FakeClient(payload)).formalize(
            FormalizationRequest(space)
        )


def test_formalization_adapter_allows_missing_reading_provenance_without_readings():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
    )
    payload = {
        "candidates": [
            {
                "id": "position",
                "label": "closed position",
                "formalization_id": "closed-position",
                "context_id": "door-context",
                "formalization": None,
            }
        ]
    }

    candidates = OpenAICompatibleFormalizationProvider(FakeClient(payload)).formalize(
        FormalizationRequest(space)
    )

    assert candidates[0].reading_id is None


def test_formalization_adapter_rejects_unknown_expression_kind():
    space = InterpretationSpace(
        id="space",
        source_text="Question",
        conceptual_depth=ConceptualDepth.Ordinary,
    )
    payload = {
        "candidates": [
            {
                "id": "candidate",
                "label": "candidate",
                "formalization_id": "formal",
                "context_id": "context",
                "formalization": {"kind": "verdict", "value": "T"},
            }
        ]
    }

    with pytest.raises(ProviderSchemaError, match="unsupported"):
        OpenAICompatibleFormalizationProvider(FakeClient(payload)).formalize(
            FormalizationRequest(space)
        )
