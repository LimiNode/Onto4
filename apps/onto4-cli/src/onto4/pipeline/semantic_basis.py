"""Research-only, profile-relative adjudication bases.

The structural binding protocol says which host target a provider named.  This
module answers a narrower question: given a host-owned, normalized record of
the commitments expressed by a successor snapshot, does that record preserve
one of two frozen case profiles?

The basis is not a text classifier and is not a universal Onto4 oracle.  The
adjudicator (or another host-side procedure) must provide normalized
commitments; this module only applies the versioned profile and records why a
decision is verified, contradicted, unverified or not comparable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .semantic_adjudication import AdjudicationDecision
from .semantic_binding import BindingRelation, CheckStatus


class BasisSchemaError(ValueError):
    """A profile-relative evidence record is not a valid host-side envelope."""


class CommitmentState(str, Enum):
    AFFIRMED = "affirmed"
    DENIED = "denied"
    UNSPECIFIED = "unspecified"


@dataclass(frozen=True)
class BasisCriterion:
    """One commitment that a profile requires to be preserved."""

    key: str
    expected: CommitmentState

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("A basis criterion key must be a non-empty string.")
        if not isinstance(self.expected, CommitmentState):
            raise ValueError("A basis criterion expected state must be CommitmentState.")


@dataclass(frozen=True)
class ProfileRelativeAdjudicationBasis:
    """Versioned criteria for one bounded case and host target."""

    basis_id: str
    version: int
    case_id: str
    target_id: str
    relation: BindingRelation
    criteria: tuple[BasisCriterion, ...]

    def __post_init__(self) -> None:
        for field_name in ("basis_id", "case_id", "target_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Basis field {field_name!r} must be non-empty.")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Basis version must be a positive integer.")
        if not isinstance(self.relation, BindingRelation):
            raise ValueError("Basis relation must be a BindingRelation.")
        if self.relation is BindingRelation.NO_BINDING:
            raise ValueError("A profile-relative basis requires a binding relation.")
        if not self.criteria:
            raise ValueError("A profile-relative basis requires at least one criterion.")
        keys = [criterion.key for criterion in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("A profile-relative basis cannot repeat criterion keys.")

    def payload(self) -> dict[str, Any]:
        """Return the canonical, public description used for hashing."""

        return {
            "basis_id": self.basis_id,
            "version": self.version,
            "case_id": self.case_id,
            "target_id": self.target_id,
            "relation": self.relation.value,
            "criteria": [
                {"key": criterion.key, "expected": criterion.expected.value}
                for criterion in sorted(self.criteria, key=lambda item: item.key)
            ],
        }

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            self.payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @property
    def basis_digest(self) -> str:
        """Name the digest as it appears in PR #41 receipts."""

        return self.digest


@dataclass(frozen=True)
class ProfileAdjudicationEvidence:
    """Host-normalized commitments; no provider text is interpreted here."""

    case_id: str
    target_id: str
    relation: BindingRelation
    commitments: Mapping[str, CommitmentState]


@dataclass(frozen=True)
class ProfileAdjudicationEvaluation:
    basis: ProfileRelativeAdjudicationBasis | None
    evidence: ProfileAdjudicationEvidence | None
    schema: CheckStatus
    comparability: CheckStatus
    decision: AdjudicationDecision
    missing_commitments: tuple[str, ...] = ()
    contradictory_commitments: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def _not_comparable(
    *,
    basis: ProfileRelativeAdjudicationBasis | None,
    evidence: ProfileAdjudicationEvidence | None,
    schema: CheckStatus,
    comparability: CheckStatus,
    errors: tuple[str, ...],
) -> ProfileAdjudicationEvaluation:
    return ProfileAdjudicationEvaluation(
        basis=basis,
        evidence=evidence,
        schema=schema,
        comparability=comparability,
        decision=AdjudicationDecision.NOT_COMPARABLE,
        errors=errors,
    )


def parse_profile_evidence(payload: Mapping[str, Any]) -> ProfileAdjudicationEvidence:
    """Parse an exact host-side envelope of normalized commitments."""

    if not isinstance(payload, Mapping):
        raise BasisSchemaError("Profile adjudication evidence must be an object.")
    required = {"case_id", "target_id", "relation", "commitments"}
    unknown = set(payload) - required
    missing = required - set(payload)
    if unknown:
        raise BasisSchemaError(f"Unknown profile evidence fields: {sorted(unknown)!r}.")
    if missing:
        raise BasisSchemaError(f"Missing profile evidence fields: {sorted(missing)!r}.")
    values: dict[str, CommitmentState] = {}
    commitments = payload["commitments"]
    if not isinstance(commitments, Mapping):
        raise BasisSchemaError("Profile evidence commitments must be an object.")
    for key, value in commitments.items():
        if not isinstance(key, str) or not key.strip():
            raise BasisSchemaError("Profile evidence commitment keys must be non-empty strings.")
        try:
            values[key] = CommitmentState(value)
        except (TypeError, ValueError) as exc:
            raise BasisSchemaError(f"Unsupported commitment state for {key!r}.") from exc
    try:
        relation = BindingRelation(payload["relation"])
    except (TypeError, ValueError) as exc:
        raise BasisSchemaError("Profile evidence relation is unsupported.") from exc
    for field in ("case_id", "target_id"):
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise BasisSchemaError(f"Profile evidence field {field!r} must be non-empty.")
    return ProfileAdjudicationEvidence(
        case_id=payload["case_id"],
        target_id=payload["target_id"],
        relation=relation,
        commitments=values,
    )


def evaluate_profile_basis(
    evidence: ProfileAdjudicationEvidence | Mapping[str, Any] | None,
    *,
    basis: ProfileRelativeAdjudicationBasis,
) -> ProfileAdjudicationEvaluation:
    """Apply one profile without making a claim about universal meaning."""

    if evidence is None:
        return _not_comparable(
            basis=basis,
            evidence=None,
            schema=CheckStatus.NOT_APPLICABLE,
            comparability=CheckStatus.NOT_APPLICABLE,
            errors=("No profile-relative adjudication evidence was supplied.",),
        )
    if isinstance(evidence, Mapping):
        try:
            evidence = parse_profile_evidence(evidence)
        except BasisSchemaError as exc:
            return _not_comparable(
                basis=basis,
                evidence=None,
                schema=CheckStatus.INVALID,
                comparability=CheckStatus.NOT_APPLICABLE,
                errors=(str(exc),),
            )
    if not isinstance(evidence, ProfileAdjudicationEvidence):
        return _not_comparable(
            basis=basis,
            evidence=None,
            schema=CheckStatus.INVALID,
            comparability=CheckStatus.NOT_APPLICABLE,
            errors=("Profile evidence has an unsupported host-side type.",),
        )
    if (
        evidence.case_id != basis.case_id
        or evidence.target_id != basis.target_id
        or evidence.relation is not basis.relation
    ):
        return _not_comparable(
            basis=basis,
            evidence=evidence,
            schema=CheckStatus.VALID,
            comparability=CheckStatus.INVALID,
            errors=("Evidence does not match the profile case, target or relation.",),
        )

    criterion_keys = {criterion.key for criterion in basis.criteria}
    unknown = sorted(set(evidence.commitments) - criterion_keys)
    if unknown:
        return _not_comparable(
            basis=basis,
            evidence=evidence,
            schema=CheckStatus.INVALID,
            comparability=CheckStatus.VALID,
            errors=(f"Evidence contains unknown profile commitments: {unknown!r}.",),
        )
    missing: list[str] = []
    contradictory: list[str] = []
    for criterion in basis.criteria:
        observed = evidence.commitments.get(criterion.key, CommitmentState.UNSPECIFIED)
        if not isinstance(observed, CommitmentState):
            return _not_comparable(
                basis=basis,
                evidence=evidence,
                schema=CheckStatus.INVALID,
                comparability=CheckStatus.VALID,
                errors=(f"Evidence commitment {criterion.key!r} is not normalized.",),
            )
        if observed is CommitmentState.UNSPECIFIED:
            missing.append(criterion.key)
        elif observed is not criterion.expected:
            contradictory.append(criterion.key)
    if contradictory:
        decision = AdjudicationDecision.CONTRADICTED
    elif missing:
        decision = AdjudicationDecision.UNVERIFIED
    else:
        decision = AdjudicationDecision.VERIFIED
    return ProfileAdjudicationEvaluation(
        basis=basis,
        evidence=evidence,
        schema=CheckStatus.VALID,
        comparability=CheckStatus.VALID,
        decision=decision,
        missing_commitments=tuple(missing),
        contradictory_commitments=tuple(contradictory),
    )


GENOME_IDENTITY_BASIS = ProfileRelativeAdjudicationBasis(
    basis_id="genome-identity-bounded",
    version=1,
    case_id="genome-identity-bounded",
    target_id="ambiguity-genome",
    relation=BindingRelation.ANCHORED_UPDATE,
    criteria=(
        BasisCriterion("identity_criterion_is_numerical", CommitmentState.AFFIRMED),
        BasisCriterion("shared_genome_is_not_sufficient", CommitmentState.AFFIRMED),
        BasisCriterion("distinct_persons_can_share_genome", CommitmentState.AFFIRMED),
    ),
)


INTRINSIC_TIME_BASIS = ProfileRelativeAdjudicationBasis(
    basis_id="intrinsic-time-bounded",
    version=1,
    case_id="intrinsic-time-bounded",
    target_id="ambiguity-present",
    relation=BindingRelation.ANCHORED_UPDATE,
    criteria=(
        BasisCriterion("present_is_observer_independent", CommitmentState.AFFIRMED),
        BasisCriterion("sequence_order_alone_is_not_the_present", CommitmentState.AFFIRMED),
    ),
)


PROFILE_RELATIVE_BASES = {
    GENOME_IDENTITY_BASIS.basis_id: GENOME_IDENTITY_BASIS,
    INTRINSIC_TIME_BASIS.basis_id: INTRINSIC_TIME_BASIS,
}


__all__ = [
    "BasisCriterion",
    "BasisSchemaError",
    "CommitmentState",
    "GENOME_IDENTITY_BASIS",
    "INTRINSIC_TIME_BASIS",
    "PROFILE_RELATIVE_BASES",
    "ProfileAdjudicationEvaluation",
    "ProfileAdjudicationEvidence",
    "ProfileRelativeAdjudicationBasis",
    "evaluate_profile_basis",
    "parse_profile_evidence",
]
