"""Research-only validation of independently normalized semantic evidence.

This module sits between a private adjudication procedure and a public
adjudication receipt.  A normalizer may inspect source material that must not
be published, but it can publish an opaque source digest and normalized
commitments.  The host verifies that the record belongs to one concrete,
structurally admissible transition and one versioned profile-relative basis,
and that its source digest matches a host-owned source manifest.

It does not read provider prose, infer commitments from a binding claim, or
turn a normalization record into a semantic-adjudication receipt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .semantic_adjudication import AdjudicationDecision
from .semantic_basis import (
    ProfileAdjudicationEvaluation,
    ProfileRelativeAdjudicationBasis,
    evaluate_profile_basis,
)
from .semantic_binding import (
    BindingEvaluation,
    BindingRelation,
    BindingTransition,
    CheckStatus,
)


class EvidenceNormalizationSchemaError(ValueError):
    """A normalized-evidence record is not a valid host-side envelope."""


_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class IndependentEvidenceNormalization:
    """A redaction-safe, independently normalized evidence record.

    ``source_digest`` identifies the material inspected by the normalizer.  It
    is not provider text, an oracle response, or evidence of semantic identity
    by itself.
    """

    case_id: str
    previous_snapshot_id: str
    current_snapshot_id: str
    target_id: str
    question_id: str
    answer_ids: tuple[str, ...]
    relation: BindingRelation
    basis_digest: str
    normalizer_id: str
    normalizer_version: str
    source_digest: str
    commitments: Mapping[str, str]


@dataclass(frozen=True)
class EvidenceNormalizationEvaluation:
    """Validation results for a normalization record, not an Onto4 verdict."""

    normalization: IndependentEvidenceNormalization | None
    profile_evaluation: ProfileAdjudicationEvaluation | None
    schema: CheckStatus
    provenance: CheckStatus
    origin: CheckStatus
    independence: CheckStatus
    decision: AdjudicationDecision
    errors: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Whether this record is valid evidence for a later receipt stage."""

        return (
            self.schema is CheckStatus.VALID
            and self.provenance is CheckStatus.VALID
            and self.origin is CheckStatus.VALID
            and self.independence is CheckStatus.VALID
            and self.decision is not AdjudicationDecision.NOT_COMPARABLE
        )


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceNormalizationSchemaError(
            f"Evidence normalization field {field!r} must be a non-empty string."
        )
    return value


def parse_independent_evidence_normalization(
    payload: Mapping[str, Any],
) -> IndependentEvidenceNormalization:
    """Parse one exact public envelope without accepting raw source content."""

    if not isinstance(payload, Mapping):
        raise EvidenceNormalizationSchemaError("Evidence normalization must be an object.")
    required = {
        "case_id",
        "previous_snapshot_id",
        "current_snapshot_id",
        "target_id",
        "question_id",
        "answer_ids",
        "relation",
        "basis_digest",
        "normalizer_id",
        "normalizer_version",
        "source_digest",
        "commitments",
    }
    unknown = [key for key in payload if key not in required]
    missing = required - set(payload)
    if unknown:
        raise EvidenceNormalizationSchemaError(
            f"Unknown evidence normalization fields: {unknown!r}."
        )
    if missing:
        raise EvidenceNormalizationSchemaError(
            f"Missing evidence normalization fields: {sorted(missing)!r}."
        )
    answer_ids = payload["answer_ids"]
    if (
        not isinstance(answer_ids, list)
        or not answer_ids
        or any(not isinstance(answer_id, str) or not answer_id.strip() for answer_id in answer_ids)
        or len(set(answer_ids)) != len(answer_ids)
    ):
        raise EvidenceNormalizationSchemaError(
            "Evidence normalization answer_ids must be a unique non-empty list of strings."
        )
    commitments = payload["commitments"]
    if not isinstance(commitments, Mapping):
        raise EvidenceNormalizationSchemaError("Evidence normalization commitments must be an object.")
    values: dict[str, str] = {}
    for key, value in commitments.items():
        if not isinstance(key, str) or not key.strip():
            raise EvidenceNormalizationSchemaError(
                "Evidence normalization commitment keys must be non-empty strings."
            )
        if not isinstance(value, str):
            raise EvidenceNormalizationSchemaError(
                f"Evidence normalization state for {key!r} must be a string."
            )
        values[key] = value
    try:
        relation = BindingRelation(_required_string(payload, "relation"))
    except ValueError as exc:
        raise EvidenceNormalizationSchemaError(
            "Evidence normalization relation is unsupported."
        ) from exc
    basis_digest = _required_string(payload, "basis_digest")
    source_digest = _required_string(payload, "source_digest")
    if _SHA256.fullmatch(basis_digest) is None:
        raise EvidenceNormalizationSchemaError(
            "Evidence normalization basis_digest must be a lowercase SHA-256 digest."
        )
    if _SHA256.fullmatch(source_digest) is None:
        raise EvidenceNormalizationSchemaError(
            "Evidence normalization source_digest must be a lowercase SHA-256 digest."
        )
    return IndependentEvidenceNormalization(
        case_id=_required_string(payload, "case_id"),
        previous_snapshot_id=_required_string(payload, "previous_snapshot_id"),
        current_snapshot_id=_required_string(payload, "current_snapshot_id"),
        target_id=_required_string(payload, "target_id"),
        question_id=_required_string(payload, "question_id"),
        answer_ids=tuple(answer_ids),
        relation=relation,
        basis_digest=basis_digest,
        normalizer_id=_required_string(payload, "normalizer_id"),
        normalizer_version=_required_string(payload, "normalizer_version"),
        source_digest=source_digest,
        commitments=values,
    )


def _not_comparable(
    *,
    normalization: IndependentEvidenceNormalization | None,
    profile_evaluation: ProfileAdjudicationEvaluation | None,
    schema: CheckStatus,
    provenance: CheckStatus,
    origin: CheckStatus,
    independence: CheckStatus,
    errors: tuple[str, ...],
) -> EvidenceNormalizationEvaluation:
    return EvidenceNormalizationEvaluation(
        normalization=normalization,
        profile_evaluation=profile_evaluation,
        schema=schema,
        provenance=provenance,
        origin=origin,
        independence=independence,
        decision=AdjudicationDecision.NOT_COMPARABLE,
        errors=errors,
    )


def evaluate_independent_evidence_normalization(
    payload: Mapping[str, Any] | None,
    *,
    basis: ProfileRelativeAdjudicationBasis,
    binding: BindingEvaluation,
    transition: BindingTransition,
    provider_id: str,
    expected_source_digest: str,
    trusted_normalizer_registry: Mapping[str, str],
    origin_attested: bool,
) -> EvidenceNormalizationEvaluation:
    """Validate evidence before applying its profile-relative commitments.

    ``expected_source_digest`` comes from a host-owned source manifest; the
    normalizer's claimed digest is not trusted on its own. The host must
    attest the normalizer's channel separately.  A provider
    cannot normalize its own binding claim, and a structural claim without a
    complete transition match cannot be upgraded by this record.
    """

    if not isinstance(provider_id, str) or not provider_id.strip():
        return _not_comparable(
            normalization=None,
            profile_evaluation=None,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.INVALID,
            origin=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.INVALID,
            errors=("Provider identity is required for an independence check.",),
        )
    if not isinstance(expected_source_digest, str) or _SHA256.fullmatch(expected_source_digest) is None:
        return _not_comparable(
            normalization=None,
            profile_evaluation=None,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.INVALID,
            origin=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=("Host expected_source_digest must be a lowercase SHA-256 digest.",),
        )
    if not isinstance(origin_attested, bool) or not origin_attested:
        return _not_comparable(
            normalization=None,
            profile_evaluation=None,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.NOT_APPLICABLE,
            origin=CheckStatus.INVALID,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=("Host trusted-origin attestation is required for normalization.",),
        )
    if not binding.structurally_admissible or binding.claim is None:
        return _not_comparable(
            normalization=None,
            profile_evaluation=None,
            schema=CheckStatus.NOT_APPLICABLE,
            provenance=CheckStatus.NOT_APPLICABLE,
            origin=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=("Evidence normalization requires a structurally admissible binding claim.",),
        )
    if payload is None:
        return _not_comparable(
            normalization=None,
            profile_evaluation=None,
            schema=CheckStatus.NOT_APPLICABLE,
            provenance=CheckStatus.NOT_APPLICABLE,
            origin=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=("No independent evidence normalization was supplied.",),
        )
    try:
        normalization = parse_independent_evidence_normalization(payload)
    except EvidenceNormalizationSchemaError as exc:
        return _not_comparable(
            normalization=None,
            profile_evaluation=None,
            schema=CheckStatus.INVALID,
            provenance=CheckStatus.NOT_APPLICABLE,
            origin=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=(str(exc),),
        )

    claim = binding.claim
    if (
        normalization.previous_snapshot_id != transition.previous.id
        or normalization.current_snapshot_id != transition.current.id
        or normalization.question_id != transition.question.id
        or normalization.previous_snapshot_id != binding.evaluated_previous_snapshot_id
        or normalization.current_snapshot_id != binding.evaluated_current_snapshot_id
        or normalization.question_id != binding.evaluated_question_id
        or normalization.target_id != claim.target_id
        or normalization.relation is not claim.relation
        or normalization.basis_digest != basis.basis_digest
        or normalization.source_digest != expected_source_digest
    ):
        return _not_comparable(
            normalization=normalization,
            profile_evaluation=None,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.INVALID,
            origin=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.NOT_APPLICABLE,
            errors=("Normalization does not match the host transition, claim, basis or source manifest.",),
        )
    if normalization.normalizer_id == provider_id:
        return _not_comparable(
            normalization=normalization,
            profile_evaluation=None,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.VALID,
            origin=CheckStatus.NOT_APPLICABLE,
            independence=CheckStatus.INVALID,
            errors=("The provider cannot independently normalize its own output.",),
        )
    expected_version = trusted_normalizer_registry.get(normalization.normalizer_id)
    if expected_version != normalization.normalizer_version:
        return _not_comparable(
            normalization=normalization,
            profile_evaluation=None,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.VALID,
            origin=CheckStatus.INVALID,
            independence=CheckStatus.VALID,
            errors=("Normalizer identity or version is not trusted by the host.",),
        )
    profile_evaluation = evaluate_profile_basis(
        {
            "case_id": normalization.case_id,
            "target_id": normalization.target_id,
            "question_id": normalization.question_id,
            "answer_ids": list(normalization.answer_ids),
            "relation": normalization.relation.value,
            "commitments": normalization.commitments,
        },
        basis=basis,
    )
    if profile_evaluation.decision is AdjudicationDecision.NOT_COMPARABLE:
        return _not_comparable(
            normalization=normalization,
            profile_evaluation=profile_evaluation,
            schema=profile_evaluation.schema,
            provenance=CheckStatus.VALID,
            origin=CheckStatus.VALID,
            independence=CheckStatus.VALID,
            errors=profile_evaluation.errors,
        )
    return EvidenceNormalizationEvaluation(
        normalization=normalization,
        profile_evaluation=profile_evaluation,
        schema=CheckStatus.VALID,
        provenance=CheckStatus.VALID,
        origin=CheckStatus.VALID,
        independence=CheckStatus.VALID,
        decision=profile_evaluation.decision,
    )


__all__ = [
    "EvidenceNormalizationEvaluation",
    "EvidenceNormalizationSchemaError",
    "IndependentEvidenceNormalization",
    "evaluate_independent_evidence_normalization",
    "parse_independent_evidence_normalization",
]
