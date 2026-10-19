import json
import gc
from pathlib import Path

import pytest

from onto4.core import PredicateExpr
from onto4.providers import (
    AssessmentContextProjection,
    FormalizationRequest,
    InterpretationRequest,
    OpenAICompatibleFormalizationProvider,
    OpenAICompatibleInterpretationProvider,
    OpenAICompatibleRefinementDeltaProvider,
    ProviderSchemaError,
)
from onto4.pipeline import host_semantic_target_bindings, load_clarification_corpus
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
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


def test_refinement_delta_adapter_returns_only_bounded_operation_content():
    client = FakeClient(
        {
            "deltas": [{
                "operation": "select_reading",
                "target_id": "reading-0",
                "resolved_ambiguity_ids": ["ambiguity-0"],
            }]
        }
    )
    interpretation = InterpretationSpace(
        "space",
        "The door is closed.",
        ConceptualDepth.Ordinary,
        ambiguities=(Ambiguity("ambiguity-0", "closed", "position or lock"),),
        readings=(SemanticReading("reading-0", "position", "not open"),),
    )
    question = ClarificationQuestion(
        "meaning:ambiguity-0",
        ClarificationKind.Meaning,
        "What does closed mean?",
        ("ambiguity-0",),
    )

    deltas = OpenAICompatibleRefinementDeltaProvider(client).propose_refinement_deltas(
        interpretation,
        question,
        "not open",
        allowed_operations=("select_reading", "abstain"),
        allowed_reading_ids=("reading-0",),
        allowed_ambiguity_ids=("ambiguity-0",),
        allowed_ontology_ids=(),
    )

    assert deltas[0]["operation"] == "select_reading"
    prompt = client.messages[1]["content"]
    assert "reading-0" in prompt
    assert "ambiguity-0" in prompt
    assert "Do not return a successor snapshot" in prompt
    assert "Onto4 verdict" in prompt


def test_refinement_delta_adapter_rejects_snapshot_or_verdict_fields():
    payload = {
        "deltas": [
            {"operation": "abstain", "successor": {}, "verdict": "T"}
        ]
    }
    provider = OpenAICompatibleRefinementDeltaProvider(FakeClient(payload))
    interpretation = InterpretationSpace(
        "space", "The door is closed.", ConceptualDepth.Ordinary
    )
    question = ClarificationQuestion(
        "question", ClarificationKind.Meaning, "Clarify", ()
    )

    with pytest.raises(ProviderSchemaError, match="unknown fields"):
        provider.propose_refinement_deltas(
            interpretation,
            question,
            "none",
            allowed_operations=("abstain",),
            allowed_reading_ids=(),
            allowed_ambiguity_ids=(),
            allowed_ontology_ids=(),
        )


def test_refinement_delta_adapter_rejects_empty_batch():
    provider = OpenAICompatibleRefinementDeltaProvider(FakeClient({"deltas": []}))
    interpretation = InterpretationSpace(
        "space", "The door is closed.", ConceptualDepth.Ordinary
    )
    question = ClarificationQuestion(
        "question", ClarificationKind.Meaning, "Clarify", ()
    )

    with pytest.raises(ProviderSchemaError, match="non-empty JSON array"):
        provider.propose_refinement_deltas(
            interpretation,
            question,
            "none",
            allowed_operations=("abstain",),
            allowed_reading_ids=(),
            allowed_ambiguity_ids=(),
            allowed_ontology_ids=(),
        )


def test_refinement_delta_adapter_rejects_batch_over_host_operation_limit():
    from onto4.providers import MAX_REFINEMENT_OPERATIONS

    provider = OpenAICompatibleRefinementDeltaProvider(
        FakeClient(
            {
                "deltas": [
                    {"operation": "abstain"}
                    for _ in range(MAX_REFINEMENT_OPERATIONS + 1)
                ]
            }
        )
    )
    interpretation = InterpretationSpace(
        "space", "The door is closed.", ConceptualDepth.Ordinary
    )
    question = ClarificationQuestion(
        "question", ClarificationKind.Meaning, "Clarify", ()
    )

    with pytest.raises(ProviderSchemaError, match="operation limit"):
        provider.propose_refinement_deltas(
            interpretation,
            question,
            "none",
            allowed_operations=("abstain",),
            allowed_reading_ids=(),
            allowed_ambiguity_ids=(),
            allowed_ontology_ids=(),
        )


@pytest.mark.parametrize(
    ("variant", "marker"),
    (
        ("baseline", "requested_conceptual_depth"),
        ("explicit_depth", "Repeat the requested conceptual_depth exactly"),
        ("compact_json", '"conceptual_depth":"ordinary"'),
    ),
)
def test_interpretation_prompt_variants_are_explicitly_recordable(variant, marker):
    client = FakeClient(interpretation_payload())
    OpenAICompatibleInterpretationProvider(
        client, prompt_variant=variant
    ).interpret(InterpretationRequest("The door is closed."))

    assert marker in client.messages[1]["content"]


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


def test_interpretation_adapter_requires_explicit_host_target_reference():
    payload = interpretation_payload()
    payload["ambiguities"][0]["target_id"] = "host-target"
    provider = OpenAICompatibleInterpretationProvider(FakeClient(payload))

    result = provider.interpret(
        InterpretationRequest(
            "The door is closed.",
            state={"semantic_target_catalog": {
                "host-target": {"kind": "Meaning", "description": "door state"}
            }},
        )
    )

    assert result.ambiguities[0].id == "ambiguity-0"
    assert result.ambiguities[0].target_id == "host-target"


def test_interpretation_adapter_rejects_target_reference_with_wrong_kind():
    payload = interpretation_payload()
    payload["ambiguities"][0]["target_id"] = "ontology-target"
    with pytest.raises(ProviderSchemaError, match="wrong target kind"):
        OpenAICompatibleInterpretationProvider(FakeClient(payload)).interpret(
            InterpretationRequest(
                "The door is closed.",
                state={"semantic_target_catalog": {
                    "ontology-target": {
                        "kind": "Ontology",
                        "description": "an ontological frame",
                    }
                }},
            )
        )


def test_target_catalog_isolated_for_identical_snapshot_ids():
    client = FakeClient(interpretation_payload())
    provider = OpenAICompatibleInterpretationProvider(client)
    first_catalog = {"first": {"kind": "Meaning", "description": "first"}}
    second_catalog = {"second": {"kind": "Meaning", "description": "second"}}
    first = provider.interpret(
        InterpretationRequest("The door is closed.", state={"semantic_target_catalog": first_catalog})
    )
    second = provider.interpret(
        InterpretationRequest("The door is closed.", state={"semantic_target_catalog": second_catalog})
    )
    question = ClarificationQuestion(
        "meaning:closed", ClarificationKind.Meaning, "What does closed mean?", ("ambiguity-0",)
    )
    provider.refine(first, question, "first answer")
    assert '"first"' in client.messages[1]["content"]
    provider.refine(second, question, "second answer")
    assert '"second"' in client.messages[1]["content"]


def test_target_catalog_bindings_do_not_retain_dead_snapshots():
    client = FakeClient(interpretation_payload())
    provider = OpenAICompatibleInterpretationProvider(client)
    catalog = {"target": {"kind": "Meaning", "description": "target"}}
    snapshot = provider.interpret(
        InterpretationRequest("The door is closed.", state={"semantic_target_catalog": catalog})
    )
    assert len(provider._target_catalogs) == 1
    del snapshot
    gc.collect()
    # A subsequent lookup prunes dead weak references.
    provider._catalog_for(InterpretationSpace("other", "The door is closed.", ConceptualDepth.Ordinary))
    assert provider._target_catalogs == []


def test_interpretation_adapter_rejects_unbound_target_reference():
    payload = interpretation_payload()
    payload["ambiguities"][0]["target_id"] = "not-host-issued"

    with pytest.raises(ProviderSchemaError, match="allowed host target"):
        OpenAICompatibleInterpretationProvider(FakeClient(payload)).interpret(
            InterpretationRequest(
                "The door is closed.",
                state={"semantic_target_catalog": {
                    "host-target": {"kind": "Meaning", "description": "door state"}
                }},
            )
        )


def test_refinement_preserves_catalog_and_rejects_target_expansion():
    client = FakeClient(interpretation_payload())
    provider = OpenAICompatibleInterpretationProvider(client)
    catalog = {
        "host-target": {"kind": "Meaning", "description": "door state"}
    }
    initial = provider.interpret(
        InterpretationRequest(
            "The door is closed.",
            state={"semantic_target_catalog": catalog},
        )
    )
    client.payload = {
        **interpretation_payload(),
        "ambiguities": [{
            "term": "closed",
            "description": "position or lock",
            "target_id": "expanded-by-model",
        }],
    }
    question = ClarificationQuestion(
        "meaning:host-target",
        ClarificationKind.Meaning,
        "What does closed mean?",
        ("host-target",),
        structural_target_ids=("ambiguity-0",),
    )

    with pytest.raises(ProviderSchemaError, match="allowed host target"):
        provider.refine(initial, question, "not open")

    assert "host-target" in client.messages[1]["content"]
    assert "expanded-by-model" not in client.messages[1]["content"]


def test_bounded_corpus_ids_do_not_match_adapter_positional_ids():
    corpus = load_clarification_corpus(
        Path(__file__).parents[1] / "eval/clarification/bounded-dialogue-v1.yaml"
    )
    corpus_ids = {
        target_id
        for case_id, target_id in host_semantic_target_bindings(corpus)
    }
    provider = OpenAICompatibleInterpretationProvider(FakeClient({
        **interpretation_payload(),
        "ambiguities": [
            {"term": "first", "description": "first distinction"},
            {"term": "second", "description": "second distinction"},
        ],
    }))

    interpretation = provider.interpret(
        InterpretationRequest("The door is closed.")
    )

    assert {item.id for item in interpretation.ambiguities}.isdisjoint(corpus_ids)
    assert all(item.target_id is None for item in interpretation.ambiguities)


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


def test_interpretation_adapter_reports_finish_reason_without_response_body():
    class TruncatedClient(FakeClient):
        def complete(self, messages, **kwargs):
            self.messages = messages
            return {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": ""},
                    }
                ],
                "usage": {"completion_tokens": 1024},
            }

    events = []
    with pytest.raises(ProviderSchemaError, match="finish_reason=length"):
        OpenAICompatibleInterpretationProvider(
            TruncatedClient({}), trace=events.append
        ).interpret(InterpretationRequest("The door is closed."))

    response_event = next(event for event in events if event.phase == "response_received")
    assert response_event.detail == "finish_reason=length, completion_tokens=1024"


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


def test_interpretation_prompt_receives_bounded_context_projection():
    client = FakeClient(interpretation_payload())
    projection = AssessmentContextProjection(
        id="arithmetic",
        ontology="arithmetic",
        symbols=(("two", "Number"),),
    )

    OpenAICompatibleInterpretationProvider(client).interpret(
        InterpretationRequest(
            "The door is closed.",
            state={"context_projections": {"arithmetic": projection.as_dict()}},
        )
    )

    prompt = client.messages[1]["content"]
    assert "context_projections" in prompt
    assert "arithmetic" in prompt
    assert '"symbols"' in prompt
    assert "evidence" in prompt
    assert "verdict" in prompt


def test_interpretation_prompt_does_not_forward_oracle_state_without_projection():
    client = FakeClient(interpretation_payload())

    OpenAICompatibleInterpretationProvider(client).interpret(
        InterpretationRequest(
            "The door is closed.",
            state={
                "hidden_interpretation": "HIDDEN_ORACLE_MARKER",
                "expected_verdict": "EXPECTED_VERDICT_MARKER",
                "evidence": "EVIDENCE_MARKER",
            },
        )
    )

    prompt = client.messages[1]["content"]
    assert "HIDDEN_ORACLE_MARKER" not in prompt
    assert "EXPECTED_VERDICT_MARKER" not in prompt
    assert "EVIDENCE_MARKER" not in prompt
    assert "context_projections:" not in prompt


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
    assert "Formalize only this reading" in client.messages[1]["content"]
    assert "assumptions must contain only non-empty strings" in client.messages[1]["content"]


def test_interpretation_refinement_preserves_host_snapshot_fields_and_projects_answer():
    client = FakeClient(interpretation_payload())
    provider = OpenAICompatibleInterpretationProvider(client)
    current = provider.interpret(InterpretationRequest("The door is closed."))

    successor = provider.refine(
        current,
        ClarificationQuestion(
            id="meaning:closed",
            kind=ClarificationKind.Meaning,
            text="What does closed mean?",
            target_ids=("ambiguity-0",),
        ),
        "The door is locked.",
    )

    assert successor.source_text == current.source_text
    assert successor.conceptual_depth is current.conceptual_depth
    assert successor.id.startswith("interpretation-")
    assert "The door is locked." in client.messages[1]["content"]
    assert "current_interpretation" in client.messages[1]["content"]
    assert "transition history" in client.messages[1]["content"]


def test_interpretation_refinement_rejects_model_depth_change():
    payload = interpretation_payload()
    payload["conceptual_depth"] = "philosophical"

    with pytest.raises(ProviderSchemaError, match="conceptual_depth"):
        OpenAICompatibleInterpretationProvider(FakeClient(payload)).refine(
            InterpretationSpace(
                id="door-space",
                source_text="The door is closed.",
                conceptual_depth=ConceptualDepth.Ordinary,
            ),
            ClarificationQuestion(
                id="meaning:closed",
                kind=ClarificationKind.Meaning,
                text="What does closed mean?",
                target_ids=("ambiguity-0",),
            ),
            "The door is locked.",
        )


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
