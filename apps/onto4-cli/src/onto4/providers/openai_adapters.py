"""Structured OpenAI-compatible adapters for interpretation and formalization."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from onto4.core import And, Equivalent, Implies, Not, Or, PredicateCall, PredicateExpr, Term
from onto4.reasoning import (
    Ambiguity,
    ConceptualDepth,
    FormalizationCandidate,
    InterpretationSpace,
    OntologyCandidate,
    Presupposition,
    SemanticReading,
)

from .openai_compatible import OpenAICompatibleClient
from .protocols import FormalizationProvider, FormalizationRequest, InterpretationProvider, InterpretationRequest


class ProviderSchemaError(ValueError):
    """Raised when a model response does not satisfy an adapter contract."""


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProviderSchemaError(f"{path} must be a JSON object.")
    return value


def _keys(value: Mapping[str, Any], path: str, required: set[str], optional: set[str] = set()) -> None:
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise ProviderSchemaError(f"{path} is missing fields: {sorted(missing)!r}.")
    if unknown:
        raise ProviderSchemaError(f"{path} contains unknown fields: {sorted(unknown)!r}.")


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderSchemaError(f"{path} must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _string_tuple(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProviderSchemaError(f"{path} must be a JSON array.")
    return tuple(_string(item, f"{path}[{index}]") for index, item in enumerate(value))


def _response_json(client: OpenAICompatibleClient, messages: Sequence[Mapping[str, str]]) -> Mapping[str, Any]:
    envelope = client.complete(
        messages,
        response_format={"type": "json_object"},
    )
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderSchemaError("Provider response must contain a non-empty choices array.")
    choice = _object(choices[0], "choices[0]")
    message = _object(choice.get("message"), "choices[0].message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderSchemaError("choices[0].message.content must be a non-empty JSON string.")
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProviderSchemaError("Model message content is not valid JSON.") from exc
    return _object(decoded, "message.content")


def _parse_description_items(
    value: Any,
    path: str,
    constructor: Any,
) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise ProviderSchemaError(f"{path} must be a JSON array.")
    result = []
    for index, raw in enumerate(value):
        item = _object(raw, f"{path}[{index}]")
        optional = {"term"} if constructor is Ambiguity else set()
        _keys(item, f"{path}[{index}]", {"id", "description"}, optional)
        identifier = _string(item["id"], f"{path}[{index}].id")
        description = _string(item["description"], f"{path}[{index}].description")
        if constructor is Ambiguity:
            result.append(constructor(identifier, _string(item.get("term"), f"{path}[{index}].term"), description))
        else:
            result.append(constructor(identifier, description))
    return tuple(result)


def _parse_ontology_candidates(value: Any) -> tuple[OntologyCandidate, ...]:
    if not isinstance(value, list):
        raise ProviderSchemaError("ontologies must be a JSON array.")
    result = []
    for index, raw in enumerate(value):
        item = _object(raw, f"ontologies[{index}]")
        _keys(item, f"ontologies[{index}]", {"id", "label", "description"})
        result.append(
            OntologyCandidate(
                _string(item["id"], f"ontologies[{index}].id"),
                _string(item["label"], f"ontologies[{index}].label"),
                _string(item["description"], f"ontologies[{index}].description"),
            )
        )
    return tuple(result)


def _parse_readings(value: Any) -> tuple[SemanticReading, ...]:
    if not isinstance(value, list):
        raise ProviderSchemaError("readings must be a JSON array.")
    result = []
    for index, raw in enumerate(value):
        item = _object(raw, f"readings[{index}]")
        _keys(item, f"readings[{index}]", {"id", "label", "description"}, {"presupposition_ids"})
        result.append(
            SemanticReading(
                _string(item["id"], f"readings[{index}].id"),
                _string(item["label"], f"readings[{index}].label"),
                _string(item["description"], f"readings[{index}].description"),
                _string_tuple(item.get("presupposition_ids", []), f"readings[{index}].presupposition_ids"),
            )
        )
    return tuple(result)


def _parse_interpretation(payload: Mapping[str, Any], request: InterpretationRequest) -> InterpretationSpace:
    _keys(
        payload,
        "interpretation",
        {"id", "source_text", "conceptual_depth", "ambiguities", "presuppositions", "ontologies", "readings"},
    )
    source_text = _string(payload["source_text"], "source_text")
    if source_text != request.source_text:
        raise ProviderSchemaError("Model source_text does not match the interpretation request.")
    try:
        depth = ConceptualDepth(_string(payload["conceptual_depth"], "conceptual_depth"))
    except ValueError as exc:
        raise ProviderSchemaError("conceptual_depth is not a supported ConceptualDepth.") from exc
    return InterpretationSpace(
        id=_string(payload["id"], "id"),
        source_text=source_text,
        conceptual_depth=depth,
        ambiguities=_parse_description_items(payload["ambiguities"], "ambiguities", Ambiguity),
        presuppositions=_parse_description_items(payload["presuppositions"], "presuppositions", Presupposition),
        ontologies=_parse_ontology_candidates(payload["ontologies"]),
        readings=_parse_readings(payload["readings"]),
    )


def _parse_term(value: Any, path: str) -> Term:
    item = _object(value, path)
    _keys(item, path, {"name"}, {"declared_type"})
    return Term(_string(item["name"], f"{path}.name"), _optional_string(item.get("declared_type"), f"{path}.declared_type"))


def _parse_expr(value: Any, path: str) -> Any:
    item = _object(value, path)
    kind = _string(item.get("kind"), f"{path}.kind")
    if kind == "predicate":
        _keys(item, path, {"kind", "name", "args"})
        args = item["args"]
        if not isinstance(args, list):
            raise ProviderSchemaError(f"{path}.args must be a JSON array.")
        return PredicateExpr(PredicateCall(_string(item["name"], f"{path}.name"), tuple(_parse_term(arg, f"{path}.args[{i}]") for i, arg in enumerate(args))))
    unary = {"not": Not}
    binary = {"and": And, "or": Or, "implies": Implies, "equivalent": Equivalent}
    if kind in unary:
        _keys(item, path, {"kind", "operand"})
        return unary[kind](_parse_expr(item["operand"], f"{path}.operand"))
    if kind in binary:
        _keys(item, path, {"kind", "left", "right"})
        return binary[kind](_parse_expr(item["left"], f"{path}.left"), _parse_expr(item["right"], f"{path}.right"))
    raise ProviderSchemaError(f"{path}.kind is unsupported: {kind!r}.")


def _parse_candidates(payload: Mapping[str, Any], request: FormalizationRequest) -> tuple[FormalizationCandidate, ...]:
    _keys(payload, "formalization", {"candidates"})
    raw_candidates = payload["candidates"]
    if not isinstance(raw_candidates, list):
        raise ProviderSchemaError("candidates must be a JSON array.")
    reading_ids = {reading.id for reading in request.interpretation.readings}
    result = []
    for index, raw in enumerate(raw_candidates):
        path = f"candidates[{index}]"
        item = _object(raw, path)
        _keys(item, path, {"id", "label", "formalization_id", "context_id", "formalization"}, {"reading_id", "assumptions"})
        reading_id = _optional_string(item.get("reading_id"), f"{path}.reading_id")
        if reading_id is not None and reading_id not in reading_ids:
            raise ProviderSchemaError(f"{path}.reading_id refers to an unknown interpretation reading.")
        formalization = item["formalization"]
        parsed_formalization = None if formalization is None else _parse_expr(formalization, f"{path}.formalization")
        result.append(
            FormalizationCandidate(
                id=_string(item["id"], f"{path}.id"),
                label=_string(item["label"], f"{path}.label"),
                formalization_id=_string(item["formalization_id"], f"{path}.formalization_id"),
                context_id=_string(item["context_id"], f"{path}.context_id"),
                formalization=parsed_formalization,
                reading_id=reading_id,
                assumptions=_string_tuple(item.get("assumptions", []), f"{path}.assumptions"),
            )
        )
    return tuple(result)


class OpenAICompatibleInterpretationProvider(InterpretationProvider):
    """Build one immutable interpretation space from a structured model reply."""

    def __init__(self, client: OpenAICompatibleClient) -> None:
        self.client = client

    def interpret(self, request: InterpretationRequest) -> InterpretationSpace:
        payload = _response_json(
            self.client,
            (
                {"role": "system", "content": "Return only the requested JSON interpretation object."},
                {
                    "role": "user",
                    "content": (
                        "Interpret this source text into the exact JSON fields "
                        "id, source_text, conceptual_depth, ambiguities, presuppositions, "
                        "ontologies and readings. Do not choose a verdict.\n\n"
                        f"source_text: {request.source_text}"
                    ),
                },
            ),
        )
        return _parse_interpretation(payload, request)


class OpenAICompatibleFormalizationProvider(FormalizationProvider):
    """Build explicit formalization candidates from a structured model reply."""

    def __init__(self, client: OpenAICompatibleClient) -> None:
        self.client = client

    def formalize(self, request: FormalizationRequest) -> tuple[FormalizationCandidate, ...]:
        payload = _response_json(
            self.client,
            (
                {"role": "system", "content": "Return only the requested JSON formalization object."},
                {
                    "role": "user",
                    "content": (
                        "Formalize the supplied interpretation into a JSON object with "
                        "a candidates array. Each formalization expression uses kind "
                        "predicate/not/and/or/implies/equivalent. Do not return an Onto4 verdict.\n\n"
                        f"interpretation_id: {request.interpretation.id}\n"
                        f"source_text: {request.interpretation.source_text}"
                    ),
                },
            ),
        )
        return _parse_candidates(payload, request)


__all__ = [
    "OpenAICompatibleFormalizationProvider",
    "OpenAICompatibleInterpretationProvider",
    "ProviderSchemaError",
]
