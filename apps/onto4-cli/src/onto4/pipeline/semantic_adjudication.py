"""Research-only validation of independent semantic-adjudication receipts.

The provider's binding claim and an adjudicator's semantic assessment are two
different records.  This module validates that an assessment is tied to the
same host transition, based on the expected host-owned rubric, and issued by
an actor distinct from the provider.  It does not infer meaning from text and
does not make a receipt into a universal Onto4 oracle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .semantic_binding import (
    BindingEvaluation,
    BindingRelation,
    BindingTransition,
    CheckStatus,
)


class AdjudicationSchemaError(ValueError):
    """An adjudication receipt cannot be parsed as its host-side schema."""


class AdjudicationDecision(str, Enum):
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"
    NOT_COMPARABLE = "not_comparable"


_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class SemanticAdjudicationReceipt:
    """Host-side receipt from an independent semantic adjudicator.

    The receipt is evidence about a bounded transition, not a provider-facing
    field and not a replacement for a semantic theory.
    """

    previous_snapshot_id: str
    current_snapshot_id: str
    target_id: str
    relation: BindingRelation
    decision: AdjudicationDecision
    adjudicator_id: str
    adjudicator_version: str
    basis_digest: str


@dataclass(frozen=True)
class SemanticAdjudicationEvaluation:
    """Independent evidence and provenance checks for one adjudication."""

    receipt: SemanticAdjudicationReceipt | None
    schema: CheckStatus
    provenance: CheckStatus
    independence: CheckStatus
    decision: AdjudicationDecision
    errors: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return (
            self.decision is AdjudicationDecision.VERIFIED
            and self.schema is CheckStatus.VALID
            and self.provenance is CheckStatus.VALID
            and self.independence is CheckStatus.VALID
        )


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdjudicationSchemaError(
            f"Adjudication receipt field {field!r} must be a non-empty string."
        )
    return value


def parse_adjudication_receipt(payload: Mapping[str, Any]) -> SemanticAdjudicationReceipt:
    """Parse a receipt with an exact, fail-closed host-side envelope."""

    if not isinstance(payload, Mapping):
        raise AdjudicationSchemaError("Adjudication receipt must be an object.")
    required = {
        "previous_snapshot_id",
        "current_snapshot_id",
        "target_id",
        "relation",
        "decision",
        "adjudicator_id",
        "adjudicator_version",
        "basis_digest",
    }
    unknown = set(payload) - required
    missing = required - set(payload)
    if unknown:
        raise AdjudicationSchemaError(
            f"Unknown adjudication receipt fields: {sorted(unknown)!r}."
        )
    if missing:
        raise AdjudicationSchemaError(
            f"Missing adjudication receipt fields: {sorted(missing)!r}."
        )
    try:
        relation = BindingRelation(_required_string(payload, "relation"))
    except ValueError as exc:
        raise AdjudicationSchemaError("Adjudication receipt relation is unsupported.") from exc
    try:
        decision = AdjudicationDecision(_required_string(payload, "decision"))
    except ValueError as exc:
        raise AdjudicationSchemaError("Adjudication receipt decision is unsupported.") from exc
    basis_digest = _required_string(payload, "basis_digest")
    if _SHA256.fullmatch(basis_digest) is None:
        raise AdjudicationSchemaError("Adjudication basis_digest must be a lowercase SHA-256 digest.")
    return SemanticAdjudicationReceipt(
        previous_snapshot_id=_required_string(payload, "previous_snapshot_id"),
        current_snapshot_id=_required_string(payload, "current_snapshot_id"),
        target_id=_required_string(payload, "target_id"),
        relation=relation,
        decision=decision,
        adjudicator_id=_required_string(payload, "adjudicator_id"),
        adjudicator_version=_required_string(payload, "adjudicator_version"),
        basis_digest=basis_digest,
    )


def _invalid(
    *,
    receipt: SemanticAdjudicationReceipt | None,
    schema: CheckStatus,
    provenance: CheckStatus,
    independence: CheckStatus,
    errors: tuple[str, ...],
) -> SemanticAdjudicationEvaluation:
    return SemanticAdjudicationEvaluation(
        receipt=receipt,
        schema=schema,
        provenance=provenance,
        independence=independence,
        decision=AdjudicationDecision.NOT_COMPARABLE,
        errors=errors,
    )


def evaluate_semantic_adjudication(
    payload: Mapping[str, Any] | None,
    *,
    binding: BindingEvaluation,
    transition: BindingTransition,
    provider_id: str,
    expected_basis_digest: str,
) -> SemanticAdjudicationEvaluation:
    """Validate an independent receipt without deriving semantic meaning.

    A structurally inadmissible binding cannot be upgraded by an adjudicator
    receipt.  For an admissible binding, the receipt must match the exact host
    transition and claim, use the expected host-owned basis, and name an actor
    distinct from the provider.
    """

    if not isinstance(provider_id, str) or not provider_id.strip():
        return _invalid(
            receipt=None,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.INVALID,
            independence=CheckStatus.INVALID,
            errors=("Provider identity is required for an independence check.",),
        )
    if _SHA256.fullmatch(expected_basis_digest) is None:
        return _invalid(
            receipt=None,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.INVALID,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=("Expected adjudication basis must be a lowercase SHA-256 digest.",),
        )
    if not binding.structurally_admissible or binding.claim is None:
        return _invalid(
            receipt=None,
            schema=CheckStatus.NOT_APPLICABLE,
            provenance=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=("Semantic adjudication requires a structurally admissible binding claim.",),
        )
    if payload is None:
        return SemanticAdjudicationEvaluation(
            receipt=None,
            schema=CheckStatus.NOT_APPLICABLE,
            provenance=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.NOT_APPLICABLE,
            decision=AdjudicationDecision.NOT_COMPARABLE,
            errors=("No independent adjudication receipt was supplied.",),
        )
    try:
        receipt = parse_adjudication_receipt(payload)
    except AdjudicationSchemaError as exc:
        return _invalid(
            receipt=None,
            schema=CheckStatus.INVALID,
            provenance=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=(str(exc),),
        )

    errors: list[str] = []
    provenance_status = CheckStatus.VALID
    independence_status = CheckStatus.VALID
    claim = binding.claim
    if (
        receipt.previous_snapshot_id != transition.previous.id
        or receipt.current_snapshot_id != transition.current.id
    ):
        provenance_status = CheckStatus.INVALID
        errors.append("Adjudication receipt snapshot lineage does not match the host transition.")
    if receipt.target_id != claim.target_id or receipt.relation is not claim.relation:
        provenance_status = CheckStatus.INVALID
        errors.append("Adjudication receipt target relation does not match the binding claim.")
    if receipt.basis_digest != expected_basis_digest:
        provenance_status = CheckStatus.INVALID
        errors.append("Adjudication receipt basis does not match the host-owned basis.")
    if receipt.adjudicator_id == provider_id:
        independence_status = CheckStatus.INVALID
        errors.append("Adjudicator identity must be distinct from provider identity.")
    decision = receipt.decision if provenance_status is CheckStatus.VALID and independence_status is CheckStatus.VALID else AdjudicationDecision.NOT_COMPARABLE
    return SemanticAdjudicationEvaluation(
        receipt=receipt,
        schema=CheckStatus.VALID,
        provenance=provenance_status,
        independence=independence_status,
        decision=decision,
        errors=tuple(errors),
    )


__all__ = [
    "AdjudicationDecision",
    "AdjudicationSchemaError",
    "SemanticAdjudicationEvaluation",
    "SemanticAdjudicationReceipt",
    "evaluate_semantic_adjudication",
    "parse_adjudication_receipt",
]
