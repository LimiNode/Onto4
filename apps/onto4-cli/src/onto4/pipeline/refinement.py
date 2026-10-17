"""Bounded, host-applied semantic refinement deltas.

This module is an opt-in research boundary.  A model can propose operation
content, but it cannot choose authoritative IDs, assessment snapshots or
verdicts.  The host validates and applies a delta to one immutable
``InterpretationSpace`` snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable, Mapping

from onto4.reasoning import (
    Ambiguity,
    InterpretationSpace,
    OntologyCandidate,
    Presupposition,
    SemanticReading,
)


class RefinementOperation(str, Enum):
    SELECT_READING = "select_reading"
    RETAIN_AMBIGUITY = "retain_ambiguity"
    REFINE_AMBIGUITY = "refine_ambiguity"
    ADD_PRESUPPOSITION = "add_presupposition"
    QUALIFY_ONTOLOGY_CANDIDATE = "qualify_ontology_candidate"
    ABSTAIN = "abstain"


class RefinementEffect(str, Enum):
    APPLIED = "applied"
    ABSTAINED = "abstained"
    NO_EFFECT = "no_effect"


class RefinementValidationError(ValueError):
    """A model delta cannot be admitted against the host snapshot."""


@dataclass(frozen=True)
class RefinementDelta:
    """Model-proposed operation content; IDs are references, never inventions."""

    operation: RefinementOperation
    target_id: str | None = None
    text: str | None = None
    label: str | None = None
    description: str | None = None
    reason: str | None = None
    resolved_ambiguity_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.operation, RefinementOperation):
            raise RefinementValidationError("operation must be a RefinementOperation.")
        for name in ("target_id", "text", "label", "description", "reason"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise RefinementValidationError(
                    f"{name} must be a string when supplied."
                )
        if not isinstance(self.resolved_ambiguity_ids, tuple):
            raise RefinementValidationError(
                "resolved_ambiguity_ids must be a tuple of non-empty strings."
            )
        if any(
            not isinstance(item, str) or not item
            for item in self.resolved_ambiguity_ids
        ):
            raise RefinementValidationError(
                "resolved_ambiguity_ids must be a tuple of non-empty strings."
            )
        if len(self.resolved_ambiguity_ids) != len(set(self.resolved_ambiguity_ids)):
            raise RefinementValidationError(
                "resolved_ambiguity_ids must not contain duplicates."
            )
        supplied = {
            "target_id": self.target_id is not None,
            "text": self.text is not None,
            "label": self.label is not None,
            "description": self.description is not None,
            "reason": self.reason is not None,
            "resolved_ambiguity_ids": bool(self.resolved_ambiguity_ids),
        }
        allowed_by_operation = {
            RefinementOperation.SELECT_READING: {"target_id", "resolved_ambiguity_ids"},
            RefinementOperation.RETAIN_AMBIGUITY: {"target_id", "reason"},
            RefinementOperation.REFINE_AMBIGUITY: {
                "target_id",
                "text",
                "description",
                "reason",
            },
            RefinementOperation.ADD_PRESUPPOSITION: {"description", "reason"},
            RefinementOperation.QUALIFY_ONTOLOGY_CANDIDATE: {
                "target_id",
                "description",
                "reason",
            },
            RefinementOperation.ABSTAIN: {"reason"},
        }
        unexpected = {
            name
            for name, present in supplied.items()
            if present and name not in allowed_by_operation[self.operation]
        }
        if unexpected:
            raise RefinementValidationError(
                f"{self.operation.value} does not accept fields: {sorted(unexpected)!r}."
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "RefinementDelta":
        if not isinstance(value, Mapping):
            raise RefinementValidationError("Refinement delta must be a mapping.")
        allowed = {
            "operation",
            "target_id",
            "text",
            "label",
            "description",
            "reason",
            "resolved_ambiguity_ids",
        }
        unknown = set(value) - allowed
        if unknown:
            raise RefinementValidationError(
                f"Refinement delta contains unknown fields: {sorted(unknown)!r}."
            )
        operation = value.get("operation")
        try:
            parsed_operation = RefinementOperation(operation)
        except (TypeError, ValueError) as exc:
            raise RefinementValidationError(
                f"Unsupported refinement operation: {operation!r}."
            ) from exc
        fields = {
            key: value.get(key)
            for key in ("target_id", "text", "label", "description", "reason")
        }
        if any(item is not None and not isinstance(item, str) for item in fields.values()):
            raise RefinementValidationError("Refinement operation fields must be strings.")
        resolved = value.get("resolved_ambiguity_ids", ())
        if (
            not isinstance(resolved, (list, tuple))
            or any(not isinstance(item, str) or not item for item in resolved)
        ):
            raise RefinementValidationError(
                "resolved_ambiguity_ids must be an array of non-empty strings."
            )
        return cls(
            operation=parsed_operation,
            resolved_ambiguity_ids=tuple(resolved),
            **fields,
        )


@dataclass(frozen=True)
class RefinementRequest:
    """Host-owned admissible target set for one exact interpretation snapshot."""

    interpretation: InterpretationSpace
    assessment_interpretation_id: str
    allowed_reading_ids: frozenset[str] = frozenset()
    allowed_ambiguity_ids: frozenset[str] = frozenset()
    allowed_ontology_ids: frozenset[str] = frozenset()
    allowed_presupposition_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.assessment_interpretation_id != self.interpretation.id:
            raise RefinementValidationError(
                "Refinement request is not bound to its assessment snapshot."
            )
        categories = (
            ("reading", self.allowed_reading_ids, {item.id for item in self.interpretation.readings}),
            ("ambiguity", self.allowed_ambiguity_ids, {item.id for item in self.interpretation.ambiguities}),
            ("ontology", self.allowed_ontology_ids, {item.id for item in self.interpretation.ontologies}),
            ("presupposition", self.allowed_presupposition_ids, {item.id for item in self.interpretation.presuppositions}),
        )
        for label, allowed, actual in categories:
            forged = allowed - actual
            if forged:
                raise RefinementValidationError(
                    f"Allowed {label} targets are absent from the snapshot: {sorted(forged)!r}."
                )
        all_ids = [item.id for group in (
            self.interpretation.readings,
            self.interpretation.ambiguities,
            self.interpretation.ontologies,
            self.interpretation.presuppositions,
        ) for item in group]
        if len(all_ids) != len(set(all_ids)):
            raise RefinementValidationError(
                "Refinement snapshot contains duplicate target IDs."
            )


@dataclass(frozen=True)
class RefinementCommitment:
    """Provenance record for one host-admitted delta."""

    source_interpretation_id: str
    successor_interpretation_id: str
    operation: RefinementOperation
    target_id: str | None
    effect: RefinementEffect


@dataclass(frozen=True)
class RefinementResult:
    successor: InterpretationSpace
    commitment: RefinementCommitment


@dataclass(frozen=True)
class RefinementBatchResult:
    batch_id: str
    source_interpretation_id: str
    successor: InterpretationSpace
    commitments: tuple[RefinementCommitment, ...]


@dataclass(frozen=True)
class RefinementCommitLedger:
    commitments: tuple[RefinementCommitment, ...] = ()

    def record(self, commitment: RefinementCommitment) -> "RefinementCommitLedger":
        if any(
            item.source_interpretation_id == commitment.source_interpretation_id
            and item.operation is commitment.operation
            and item.target_id == commitment.target_id
            for item in self.commitments
        ):
            raise RefinementValidationError("Refinement commitment was already recorded.")
        return replace(self, commitments=(*self.commitments, commitment))


def _require_target(
    request: RefinementRequest,
    target_id: str | None,
    allowed: frozenset[str],
    *,
    label: str,
    actual: Iterable[str],
) -> str:
    if not target_id or target_id not in allowed or target_id not in set(actual):
        raise RefinementValidationError(
            f"Unknown or inadmissible {label} target: {target_id!r}."
        )
    return target_id


def _semantic_content(interpretation: InterpretationSpace) -> tuple[object, ...]:
    return (
        interpretation.source_text,
        interpretation.conceptual_depth,
        interpretation.ambiguities,
        interpretation.presuppositions,
        interpretation.ontologies,
        interpretation.readings,
    )


def _no_effect_result(
    interpretation: InterpretationSpace,
    operation: RefinementOperation,
    target_id: str | None,
) -> RefinementResult:
    return RefinementResult(
        interpretation,
        RefinementCommitment(
            interpretation.id,
            interpretation.id,
            operation,
            target_id,
            RefinementEffect.NO_EFFECT,
        ),
    )


def _next_id(prefix: str, existing: Iterable[str]) -> str:
    used = set(existing)
    index = 0
    while f"{prefix}-{index}" in used:
        index += 1
    return f"{prefix}-{index}"


def apply_refinement_delta(
    request: RefinementRequest,
    delta: RefinementDelta,
    *,
    successor_id: str,
) -> RefinementResult:
    """Validate and apply one operation to the exact host snapshot."""

    interpretation = request.interpretation
    operation = delta.operation
    if not successor_id.strip():
        raise RefinementValidationError("successor_id must be non-empty.")

    if operation is RefinementOperation.ABSTAIN:
        commitment = RefinementCommitment(
            interpretation.id,
            interpretation.id,
            operation,
            None,
            RefinementEffect.ABSTAINED,
        )
        return RefinementResult(interpretation, commitment)

    if operation is RefinementOperation.SELECT_READING:
        target_id = _require_target(
            request,
            delta.target_id,
            request.allowed_reading_ids,
            label="reading",
            actual=(item.id for item in interpretation.readings),
        )
        selected = next(
            (reading for reading in interpretation.readings if reading.id == target_id),
            None,
        )
        if selected is None:
            raise RefinementValidationError(f"Reading target {target_id!r} is stale.")
        resolved_ids = set(delta.resolved_ambiguity_ids)
        if not resolved_ids.issubset(request.allowed_ambiguity_ids):
            raise RefinementValidationError(
                "select_reading refers to an inadmissible resolved ambiguity."
            )
        successor = replace(
            interpretation,
            id=successor_id,
            ambiguities=tuple(
                item for item in interpretation.ambiguities if item.id not in resolved_ids
            ),
            readings=(selected,),
        )
    elif operation is RefinementOperation.RETAIN_AMBIGUITY:
        target_id = _require_target(
            request,
            delta.target_id,
            request.allowed_ambiguity_ids,
            label="ambiguity",
            actual=(item.id for item in interpretation.ambiguities),
        )
        if any(ambiguity.id == target_id for ambiguity in interpretation.ambiguities):
            commitment = RefinementCommitment(
                interpretation.id,
                interpretation.id,
                operation,
                target_id,
                RefinementEffect.NO_EFFECT,
            )
            return RefinementResult(interpretation, commitment)
        raise RefinementValidationError("Retained ambiguity is not in the snapshot.")
    elif operation is RefinementOperation.REFINE_AMBIGUITY:
        target_id = _require_target(
            request,
            delta.target_id,
            request.allowed_ambiguity_ids,
            label="ambiguity",
            actual=(item.id for item in interpretation.ambiguities),
        )
        if not delta.text or not delta.description:
            raise RefinementValidationError(
                "refine_ambiguity requires non-empty text and description."
            )
        successor = replace(
            interpretation,
            id=successor_id,
            ambiguities=tuple(
                replace(
                    ambiguity,
                    term=delta.text,
                    description=delta.description,
                )
                if ambiguity.id == target_id
                else ambiguity
                for ambiguity in interpretation.ambiguities
            ),
        )
    elif operation is RefinementOperation.ADD_PRESUPPOSITION:
        if not delta.description:
            raise RefinementValidationError(
                "add_presupposition requires a non-empty description."
            )
        target_id = None
        new_id = _next_id(
            "presupposition",
            (item.id for item in interpretation.presuppositions),
        )
        successor = replace(
            interpretation,
            id=successor_id,
            presuppositions=(
                *interpretation.presuppositions,
                Presupposition(new_id, delta.description),
            ),
        )
    elif operation is RefinementOperation.QUALIFY_ONTOLOGY_CANDIDATE:
        target_id = _require_target(
            request,
            delta.target_id,
            request.allowed_ontology_ids,
            label="ontology",
            actual=(item.id for item in interpretation.ontologies),
        )
        if not delta.description:
            raise RefinementValidationError(
                "qualify_ontology_candidate requires a non-empty description."
            )
        successor = replace(
            interpretation,
            id=successor_id,
            ontologies=tuple(
                replace(candidate, description=delta.description)
                if candidate.id == target_id
                else candidate
                for candidate in interpretation.ontologies
            ),
        )
    else:  # pragma: no cover - exhaustive enum guard
        raise RefinementValidationError(f"Unsupported refinement operation: {operation!r}.")

    if _semantic_content(successor) == _semantic_content(interpretation):
        return _no_effect_result(interpretation, operation, target_id)
    if successor.id == interpretation.id:
        raise RefinementValidationError(
            "A semantic refinement requires a distinct successor_id."
        )
    commitment = RefinementCommitment(
        interpretation.id,
        successor.id,
        operation,
        target_id,
        RefinementEffect.APPLIED,
    )
    return RefinementResult(successor, commitment)


def apply_refinement_batch(
    request: RefinementRequest,
    deltas: tuple[RefinementDelta, ...],
    *,
    successor_id: str,
    batch_id: str | None = None,
) -> RefinementBatchResult:
    """Apply a bounded batch atomically, rejecting conflicting targets."""

    if not deltas:
        raise RefinementValidationError("A refinement batch must not be empty.")
    if batch_id is not None and not batch_id.strip():
        raise RefinementValidationError("batch_id must be non-empty when supplied.")
    abstentions = [delta for delta in deltas if delta.operation is RefinementOperation.ABSTAIN]
    if abstentions and len(deltas) != 1:
        raise RefinementValidationError(
            "ABSTAIN cannot be combined with other refinement operations."
        )
    seen_targets: set[str] = set()
    current = request.interpretation
    commitments: list[RefinementCommitment] = []
    for index, delta in enumerate(deltas):
        if delta.target_id is not None and delta.target_id in seen_targets:
            raise RefinementValidationError(
                f"Conflicting repeated refinement target at index {index}."
            )
        if delta.target_id is not None:
            seen_targets.add(delta.target_id)
        reading_ids = {item.id for item in current.readings}
        ambiguity_ids = {item.id for item in current.ambiguities}
        ontology_ids = {item.id for item in current.ontologies}
        presupposition_ids = {item.id for item in current.presuppositions}
        current_request = replace(
            request,
            interpretation=current,
            assessment_interpretation_id=current.id,
            allowed_reading_ids=request.allowed_reading_ids & reading_ids,
            allowed_ambiguity_ids=request.allowed_ambiguity_ids & ambiguity_ids,
            allowed_ontology_ids=request.allowed_ontology_ids & ontology_ids,
            allowed_presupposition_ids=(
                request.allowed_presupposition_ids & presupposition_ids
            ),
        )
        result = apply_refinement_delta(
            current_request,
            delta,
            successor_id=successor_id if index == len(deltas) - 1 else f"{successor_id}-{index}",
        )
        if result.commitment.effect is RefinementEffect.NO_EFFECT:
            raise RefinementValidationError("Refinement batch contains a no-effect operation.")
        current = result.successor
        commitments.append(result.commitment)
    return RefinementBatchResult(
        batch_id=batch_id or successor_id,
        source_interpretation_id=request.interpretation.id,
        successor=current,
        commitments=tuple(commitments),
    )


__all__ = [
    "RefinementCommitLedger",
    "RefinementCommitment",
    "RefinementBatchResult",
    "RefinementDelta",
    "RefinementEffect",
    "RefinementOperation",
    "RefinementRequest",
    "RefinementResult",
    "RefinementValidationError",
    "apply_refinement_batch",
    "apply_refinement_delta",
]
