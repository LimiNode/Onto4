import json

import pytest

from onto4.core import PredicateExpr
from onto4.providers import (
    AssessmentContextProjection,
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
            {"id": "model-closed", "term": "closed", "description": "position or lock"}
        ],
        "presuppositions": [],
        "ontologies": [],
        "readings": [
            {
                "id": "model-closed-position",
                "label": "closed position",
                "description": "the door leaf is not open",
                "presupposition_indexes": [],
            }
        ],
    }


def test_interpretation_adapter_parses_structured_space_and_requests_json_mode():
    client = FakeClient(interpretation_payload())
    provider = OpenAICompatibleInterpretationProvider(client)

    result = provider.interpret(InterpretationRequest("The door is closed."))

    assert result.id.startswith("interpretation-")
    assert result.conceptual_depth is ConceptualDepth.Ordinary
    assert result.ambiguities[0].id == "ambiguity-0"
    assert result.readings[0].id == "reading-0"
    assert client.messages[0]["role"] == "system"


def test_interpretation_adapter_assigns_ids_and_ignores_model_identity_claims():
    payload = interpretation_payload()
    payload["presuppositions"] = [{"id": "model-presupposition", "description": "a door exists"}]
    payload["readings"][0]["presupposition_indexes"] = [0]

    result = OpenAICompatibleInterpretationProvider(FakeClient(payload)).interpret(
        InterpretationRequest("The door is closed.")
    )
    payload["id"] = "a-different-model-id"
    payload["ambiguities"][0]["id"] = "another-model-id"
    second = OpenAICompatibleInterpretationProvider(FakeClient(payload)).interpret(
        InterpretationRequest("The door is closed.")
    )

    assert result.id.startswith("interpretation-")
    assert second.id == result.id
    assert result.ambiguities[0].id == "ambiguity-0"
    assert result.presuppositions[0].id == "presupposition-0"
    assert result.readings[0].id == "reading-0"
    assert result.readings[0].presupposition_ids == ("presupposition-0",)


def test_interpretation_adapter_rejects_invalid_presupposition_index():
    payload = interpretation_payload()
    payload["presuppositions"] = [{"description": "a door exists"}]
    payload["readings"][0]["presupposition_indexes"] = [1]

    with pytest.raises(ProviderSchemaError, match="presupposition index"):
        OpenAICompatibleInterpretationProvider(FakeClient(payload)).interpret(
            InterpretationRequest("The door is closed.")
        )


def test_interpretation_adapter_emits_safe_stage_diagnostics():
    events = []
    provider = OpenAICompatibleInterpretationProvider(
        FakeClient(interpretation_payload()), trace=events.append
    )

    provider.interpret(InterpretationRequest("The door is closed."))

    assert [event.phase for event in events] == [
        "started",
        "response_received",
        "json_valid",
        "completed",
    ]
    assert all(event.elapsed_seconds >= 0 for event in events)
    assert events[-1].detail == "schema_valid"


def test_interpretation_adapter_traces_schema_failure_without_response_body():
    payload = interpretation_payload()
    payload["unexpected"] = True
    events = []

    with pytest.raises(ProviderSchemaError):
        OpenAICompatibleInterpretationProvider(
            FakeClient(payload), trace=events.append
        ).interpret(InterpretationRequest("The door is closed."))

    assert events[-1].phase == "failed"
    assert events[-1].detail == "schema"
    assert all("unexpected" not in event.detail for event in events)


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


def test_single_reading_formalization_binds_identity_on_host():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(SemanticReading("reading-0", "closed", "not open"),),
    )
    client = FakeClient(
        {
            "label": "closed position",
            "assumptions": [],
            "formalization": {
                "kind": "predicate",
                "name": "ClosedPosition",
                "args": [{"name": "door"}],
            },
        }
    )

    candidates = OpenAICompatibleFormalizationProvider(client).formalize(
        FormalizationRequest(
            space,
            reading=space.readings[0],
            context_id="physical_objects",
        )
    )

    candidate = candidates[0]
    assert candidate.context_id == "physical_objects"
    assert candidate.reading_id == "reading-0"
    assert candidate.id.startswith("candidate-")
    assert candidate.formalization_id.startswith("formalization-")
    assert "Do not return id, reading_id, context_id" in client.messages[1]["content"]


def test_single_reading_formalization_receives_bounded_context_projection():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(SemanticReading("reading-0", "closed", "not open"),),
    )
    client = FakeClient({"formalization": None})

    OpenAICompatibleFormalizationProvider(client).formalize(
        FormalizationRequest(
            space,
            reading=space.readings[0],
            context_id="physical_objects",
            context_projection=AssessmentContextProjection(
                "physical_objects",
                "physical_objects",
                symbols=(("door", "Door"),),
            ),
        )
    )

    prompt = client.messages[1]["content"]
    assert '"ontology": "physical_objects"' in prompt
    assert '"symbols"' in prompt
    assert '"evidence"' not in prompt
    assert '"verdict"' not in prompt


def test_single_reading_formalization_rejects_model_identity_fields():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(SemanticReading("reading-0", "closed", "not open"),),
    )
    payload = {
        "id": "model-candidate",
        "formalization": None,
    }

    with pytest.raises(ProviderSchemaError, match="unknown fields"):
        OpenAICompatibleFormalizationProvider(FakeClient(payload)).formalize(
            FormalizationRequest(
                space,
                reading=space.readings[0],
                context_id="physical_objects",
            )
        )


def test_single_reading_formalization_rejects_unavailable_host_context():
    space = InterpretationSpace(
        id="door-space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(SemanticReading("reading-0", "closed", "not open"),),
    )

    with pytest.raises(ProviderSchemaError, match="not in the supplied context"):
        OpenAICompatibleFormalizationProvider(
            FakeClient({"formalization": None}),
            context_ids=("physical_objects",),
        ).formalize(
            FormalizationRequest(
                space,
                reading=space.readings[0],
                context_id="other_context",
            )
        )


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


def test_formalization_adapter_rejects_context_outside_runtime_projection():
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
                "context_id": "not-available",
                "formalization": None,
            }
        ]
    }

    with pytest.raises(ProviderSchemaError, match="unavailable assessment context"):
        OpenAICompatibleFormalizationProvider(
            FakeClient(payload), context_ids=("physical_objects",)
        ).formalize(FormalizationRequest(space))
