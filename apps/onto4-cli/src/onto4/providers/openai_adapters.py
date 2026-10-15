"""Structured OpenAI-compatible adapters for interpretation and formalization."""

from __future__ import annotations

import json
import hashlib
from time import perf_counter
from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence

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

from .openai_compatible import OpenAICompatibleClient, ProviderTransportError
from .diagnostics import ProviderTrace, ProviderStageEvent, emit_provider_trace
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


def _index_tuple(value: Any, path: str, *, upper_bound: int) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ProviderSchemaError(f"{path} must be a JSON array.")
    indexes: list[int] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int):
            raise ProviderSchemaError(f"{path}[{index}] must be a non-negative integer.")
        if item < 0 or item >= upper_bound:
            raise ProviderSchemaError(
                f"{path}[{index}] refers to an unavailable presupposition index."
            )
        indexes.append(item)
    return tuple(indexes)


def _response_json(
    client: OpenAICompatibleClient,
    messages: Sequence[Mapping[str, str]],
    *,
    trace: ProviderTrace | None = None,
    stage: str,
) -> Mapping[str, Any]:
    request_started = perf_counter()
    envelope = client.complete(
        messages,
        response_format={"type": "json_object"},
    )
    emit_provider_trace(
        trace,
        ProviderStageEvent(stage, "response_received", perf_counter() - request_started),
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
        emit_provider_trace(
            trace,
            ProviderStageEvent(stage, "json_invalid", perf_counter() - request_started),
        )
        raise ProviderSchemaError("Model message content is not valid JSON.") from exc
    emit_provider_trace(
        trace,
        ProviderStageEvent(stage, "json_valid", perf_counter() - request_started),
    )
    return _object(decoded, "message.content")


def _traced_stage(
    stage: str,
    trace: ProviderTrace | None,
    operation: Callable[[], Any],
) -> Any:
    started = perf_counter()
    emit_provider_trace(trace, ProviderStageEvent(stage, "started", 0.0))
    try:
        result = operation()
    except ProviderTransportError:
        emit_provider_trace(
            trace,
            ProviderStageEvent(stage, "failed", perf_counter() - started, "transport"),
        )
        raise
    except ProviderSchemaError:
        emit_provider_trace(
            trace,
            ProviderStageEvent(stage, "failed", perf_counter() - started, "schema"),
        )
        raise
    except Exception:
        emit_provider_trace(
            trace,
            ProviderStageEvent(stage, "failed", perf_counter() - started, "unexpected"),
        )
        raise
    emit_provider_trace(
        trace,
        ProviderStageEvent(stage, "completed", perf_counter() - started, "schema_valid"),
    )
    return result


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
        optional = {"id"}
        required = {"description"}
        if constructor is Ambiguity:
            required.add("term")
        _keys(item, f"{path}[{index}]", required, optional)
        prefix = "ambiguity" if constructor is Ambiguity else "presupposition"
        identifier = f"{prefix}-{index}"
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
        _keys(item, f"ontologies[{index}]", {"label", "description"}, {"id"})
        result.append(
            OntologyCandidate(
                f"ontology-{index}",
                _string(item["label"], f"ontologies[{index}].label"),
                _string(item["description"], f"ontologies[{index}].description"),
            )
        )
    return tuple(result)


def _parse_readings(
    value: Any,
    *,
    presupposition_ids: tuple[str, ...],
) -> tuple[SemanticReading, ...]:
    if not isinstance(value, list):
        raise ProviderSchemaError("readings must be a JSON array.")
    result = []
    for index, raw in enumerate(value):
        item = _object(raw, f"readings[{index}]")
        _keys(
            item,
            f"readings[{index}]",
            {"label", "description"},
            {"id", "presupposition_indexes"},
        )
        result.append(
            SemanticReading(
                f"reading-{index}",
                _string(item["label"], f"readings[{index}].label"),
                _string(item["description"], f"readings[{index}].description"),
                tuple(
                    presupposition_ids[presupposition_index]
                    for presupposition_index in _index_tuple(
                        item.get("presupposition_indexes", []),
                        f"readings[{index}].presupposition_indexes",
                        upper_bound=len(presupposition_ids),
                    )
                ),
            )
        )
    return tuple(result)


def _interpretation_identity(space: InterpretationSpace) -> str:
    canonical = {
        "source_text": space.source_text,
        "conceptual_depth": space.conceptual_depth.value,
        "ambiguities": [
            {"term": item.term, "description": item.description}
            for item in space.ambiguities
        ],
        "presuppositions": [item.description for item in space.presuppositions],
        "ontologies": [
            {"label": item.label, "description": item.description}
            for item in space.ontologies
        ],
        "readings": [
            {
                "label": item.label,
                "description": item.description,
                "presupposition_ids": list(item.presupposition_ids),
            }
            for item in space.readings
        ],
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"interpretation-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def _parse_interpretation(payload: Mapping[str, Any], request: InterpretationRequest) -> InterpretationSpace:
    _keys(
        payload,
        "interpretation",
        {"source_text", "conceptual_depth", "ambiguities", "presuppositions", "ontologies", "readings"},
        {"id"},
    )
    source_text = _string(payload["source_text"], "source_text")
    if source_text != request.source_text:
        raise ProviderSchemaError("Model source_text does not match the interpretation request.")
    try:
        depth = ConceptualDepth(_string(payload["conceptual_depth"], "conceptual_depth"))
    except ValueError as exc:
        raise ProviderSchemaError("conceptual_depth is not a supported ConceptualDepth.") from exc
    if request.conceptual_depth is not None and depth is not request.conceptual_depth:
        raise ProviderSchemaError(
            "Model conceptual_depth does not match the interpretation request."
        )
    space = InterpretationSpace(
        id="",
        source_text=source_text,
        conceptual_depth=depth,
        ambiguities=_parse_description_items(payload["ambiguities"], "ambiguities", Ambiguity),
        presuppositions=_parse_description_items(payload["presuppositions"], "presuppositions", Presupposition),
        ontologies=_parse_ontology_candidates(payload["ontologies"]),
        readings=_parse_readings(
            payload["readings"],
            presupposition_ids=tuple(
                item.id
                for item in _parse_description_items(
                    payload["presuppositions"], "presuppositions", Presupposition
                )
            ),
        ),
    )
    return replace(space, id=_interpretation_identity(space))


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


def _expr_projection(value: Any) -> Any:
    if isinstance(value, PredicateExpr):
        return {
            "kind": "predicate",
            "name": value.call.name,
            "args": [
                {"name": item.name, "declared_type": item.declared_type}
                for item in value.call.args
            ],
        }
    if isinstance(value, Not):
        return {"kind": "not", "operand": _expr_projection(value.operand)}
    for kind, left_name, right_name in (
        (And, "left", "right"),
        (Or, "left", "right"),
        (Implies, "left", "right"),
        (Equivalent, "left", "right"),
    ):
        if isinstance(value, kind):
            return {
                "kind": kind.__name__.lower(),
                left_name: _expr_projection(value.left),
                right_name: _expr_projection(value.right),
            }
    if value is None:
        return None
    raise TypeError(f"Unsupported expression: {type(value)!r}.")


def _host_formalization_identity(formalization: Any, assumptions: tuple[str, ...]) -> str:
    payload = {
        "formalization": _expr_projection(formalization),
        "assumptions": list(assumptions),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"formalization-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def _host_candidate_identity(
    interpretation: InterpretationSpace,
    reading_id: str,
    context_id: str,
    formalization_id: str,
) -> str:
    encoded = "|".join((interpretation.id, reading_id, context_id, formalization_id))
    return f"candidate-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


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
        if request.interpretation.readings and reading_id is None:
            raise ProviderSchemaError(
                f"{path}.reading_id is required when the interpretation supplies readings."
            )
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


def _interpretation_projection(interpretation: InterpretationSpace) -> dict[str, Any]:
    """Return the complete deterministic input projection for a formalizer."""

    return {
        "id": interpretation.id,
        "source_text": interpretation.source_text,
        "conceptual_depth": interpretation.conceptual_depth.value,
        "ambiguities": [
            {"id": item.id, "term": item.term, "description": item.description}
            for item in interpretation.ambiguities
        ],
        "presuppositions": [
            {"id": item.id, "description": item.description}
            for item in interpretation.presuppositions
        ],
        "ontologies": [
            {"id": item.id, "label": item.label, "description": item.description}
            for item in interpretation.ontologies
        ],
        "readings": [
            {
                "id": item.id,
                "label": item.label,
                "description": item.description,
                "presupposition_ids": list(item.presupposition_ids),
            }
            for item in interpretation.readings
        ],
    }


class OpenAICompatibleInterpretationProvider(InterpretationProvider):
    """Build one immutable interpretation space from a structured model reply."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        *,
        trace: ProviderTrace | None = None,
    ) -> None:
        self.client = client
        self.trace = trace

    def interpret(self, request: InterpretationRequest) -> InterpretationSpace:
        requested_depth = (
            request.conceptual_depth.value
            if request.conceptual_depth is not None
            else "auto"
        )
        depth_instruction = (
            "Preserve this requested conceptual_depth exactly."
            if request.conceptual_depth is not None
            else "Select one supported ConceptualDepth; do not infer an unsupported value."
        )
        def operation() -> InterpretationSpace:
            payload = _response_json(
                self.client,
                (
                    {"role": "system", "content": "Return only the requested JSON interpretation object."},
                    {
                        "role": "user",
                        "content": (
                            "Interpret this source text into the exact JSON fields "
                            "id, source_text, conceptual_depth, ambiguities, presuppositions, "
                            "ontologies and readings. Do not choose a verdict. "
                            f"requested_conceptual_depth: {requested_depth}. "
                            f"{depth_instruction} conceptual_depth must be exactly one of "
                            "ordinary, reflective, philosophical or ontology_sensitive. "
                            "ambiguities, presuppositions, ontologies and readings must "
                        "be arrays of JSON objects with content fields only; do not "
                        "invent authoritative IDs. Readings use label, description and "
                        "presupposition_indexes, referring to the supplied presupposition "
                        "array by zero-based position. Use this shape even when arrays "
                        "are empty: ambiguities:[{term,description}], "
                        "presuppositions:[{description}], "
                        "ontologies:[{label,description}], "
                        "readings:[{label,description,presupposition_indexes}]. "
                            "Do not use arrays of prose strings. "
                            "Return JSON only.\n\n"
                            f"source_text: {request.source_text}"
                        ),
                    },
                ),
                trace=self.trace,
                stage="interpretation",
            )
            return _parse_interpretation(payload, request)

        return _traced_stage("interpretation", self.trace, operation)


class OpenAICompatibleFormalizationProvider(FormalizationProvider):
    """Build explicit formalization candidates from a structured model reply."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        *,
        context_ids: Sequence[str] = (),
        trace: ProviderTrace | None = None,
    ) -> None:
        self.client = client
        self.context_ids = tuple(context_ids)
        self.trace = trace

    def formalize(self, request: FormalizationRequest) -> tuple[FormalizationCandidate, ...]:
        if request.reading is not None:
            return _traced_stage(
                "formalization",
                self.trace,
                lambda: self._formalize_one(request),
            )
        interpretation_json = json.dumps(
            _interpretation_projection(request.interpretation),
            ensure_ascii=False,
            sort_keys=True,
        )
        def operation() -> tuple[FormalizationCandidate, ...]:
            payload = _response_json(
                self.client,
                (
                    {"role": "system", "content": "Return only the requested JSON formalization object."},
                    {
                        "role": "user",
                        "content": (
                            "Formalize the supplied interpretation into a JSON object with "
                            "a candidates array. Each formalization expression uses kind "
                            "predicate/not/and/or/implies/equivalent. Use only the supplied "
                            "reading IDs; do not invent, rename or merge readings. Do not "
                            "return an Onto4 verdict. Each candidate must contain id, label, "
                            "formalization_id, context_id, formalization, optional reading_id "
                            "and assumptions. A predicate expression is an object with kind, "
                            "name and args; each arg has name and optional declared_type. "
                            + (
                                f"Use only these supplied context IDs: {', '.join(self.context_ids)}. "
                                if self.context_ids
                                else ""
                            )
                            + "Return JSON only.\n\n"
                            f"interpretation: {interpretation_json}"
                        ),
                    },
                ),
                trace=self.trace,
                stage="formalization",
            )
            candidates = _parse_candidates(payload, request)
            if self.context_ids:
                allowed = set(self.context_ids)
                for candidate in candidates:
                    if candidate.context_id not in allowed:
                        raise ProviderSchemaError(
                            f"Candidate {candidate.id!r} refers to an unavailable assessment context."
                        )
            return candidates

        return _traced_stage("formalization", self.trace, operation)

    def _formalize_one(
        self,
        request: FormalizationRequest,
    ) -> tuple[FormalizationCandidate, ...]:
        """Formalize one host-selected reading/context pair."""

        assert request.reading is not None
        assert request.context_id is not None
        if self.context_ids and request.context_id not in self.context_ids:
            raise ProviderSchemaError(
                f"Requested context {request.context_id!r} is not in the supplied context projection."
            )
        reading_json = json.dumps(
            {
                "id": request.reading.id,
                "label": request.reading.label,
                "description": request.reading.description,
                "presupposition_ids": list(request.reading.presupposition_ids),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        context_json = json.dumps(
            request.context_projection.as_dict()
            if request.context_projection is not None
            else {"id": request.context_id},
            ensure_ascii=False,
            sort_keys=True,
        )
        payload = _response_json(
            self.client,
            (
                {"role": "system", "content": "Return only the requested JSON formalization object."},
                {
                    "role": "user",
                    "content": (
                        "Formalize exactly the supplied semantic reading for the supplied "
                        "context. Return an object with formalization, assumptions and an "
                        "optional label. Do not return id, reading_id, context_id, "
                        "formalization_id or an Onto4 verdict; the host assigns those "
                        "fields. A formalization expression uses kind predicate/not/and/"
                        "or/implies/equivalent. A predicate has kind, name and args; each "
                        "arg has name and optional declared_type. Return JSON only.\n\n"
                        f"context_projection: {context_json}\n"
                        f"interpretation: {request.interpretation.source_text}\n"
                        f"reading: {reading_json}"
                    ),
                },
            ),
            trace=self.trace,
            stage="formalization",
        )
        _keys(payload, "formalization", {"formalization"}, {"assumptions", "label"})
        raw_formalization = payload["formalization"]
        parsed_formalization = (
            None
            if raw_formalization is None
            else _parse_expr(raw_formalization, "formalization.formalization")
        )
        assumptions = _string_tuple(payload.get("assumptions", []), "formalization.assumptions")
        formalization_id = _host_formalization_identity(parsed_formalization, assumptions)
        candidate_id = _host_candidate_identity(
            request.interpretation,
            request.reading.id,
            request.context_id,
            formalization_id,
        )
        label = _optional_string(payload.get("label"), "formalization.label")
        return (
            FormalizationCandidate(
                id=candidate_id,
                label=label or request.reading.label,
                formalization_id=formalization_id,
                context_id=request.context_id,
                formalization=parsed_formalization,
                reading_id=request.reading.id,
                assumptions=assumptions,
            ),
        )


__all__ = [
    "OpenAICompatibleFormalizationProvider",
    "OpenAICompatibleInterpretationProvider",
    "ProviderSchemaError",
]
