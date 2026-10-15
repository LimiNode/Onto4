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

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "RefinementDelta":
        allowed = {
            "operation",
            "target_id",
            "text",
            "label",
            "description",
            "reason",
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
        return cls(operation=parsed_operation, **fields)


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
) -> str:
    if not target_id or target_id not in allowed:
        raise RefinementValidationError(
            f"Unknown or inadmissible {label} target: {target_id!r}."
        )
    return target_id


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
        if any(
            value is not None
            for value in (delta.target_id, delta.text, delta.label, delta.description)
        ):
            raise RefinementValidationError("abstain does not accept operation content.")
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
            request, delta.target_id, request.allowed_reading_ids, label="reading"
        )
        selected = next(reading for reading in interpretation.readings if reading.id == target_id)
        successor = replace(
            interpretation,
            id=successor_id,
            ambiguities=(),
            readings=(selected,),
        )
    elif operation is RefinementOperation.RETAIN_AMBIGUITY:
        target_id = _require_target(
            request, delta.target_id, request.allowed_ambiguity_ids, label="ambiguity"
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
            request, delta.target_id, request.allowed_ambiguity_ids, label="ambiguity"
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

    if successor == interpretation:
        raise RefinementValidationError("Refinement delta has no semantic effect.")
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
) -> RefinementResult:
    """Apply a bounded batch atomically, rejecting conflicting targets."""

    if not deltas:
        raise RefinementValidationError("A refinement batch must not be empty.")
    seen_targets: set[tuple[RefinementOperation, str | None]] = set()
    current = request.interpretation
    commitments: list[RefinementCommitment] = []
    for index, delta in enumerate(deltas):
        key = (delta.operation, delta.target_id)
        if key in seen_targets and delta.operation is not RefinementOperation.RETAIN_AMBIGUITY:
            raise RefinementValidationError(
                f"Conflicting repeated refinement target at index {index}."
            )
        seen_targets.add(key)
        current_request = replace(
            request,
            interpretation=current,
            assessment_interpretation_id=current.id,
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
    return RefinementResult(current, commitments[-1])


__all__ = [
    "RefinementCommitLedger",
    "RefinementCommitment",
    "RefinementDelta",
    "RefinementEffect",
    "RefinementOperation",
    "RefinementRequest",
    "RefinementResult",
    "RefinementValidationError",
    "apply_refinement_batch",
    "apply_refinement_delta",
]
