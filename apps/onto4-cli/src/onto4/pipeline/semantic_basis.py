"""Research-only, profile-relative adjudication bases.

The structural binding protocol says which host target a provider named.  This
module answers a narrower question: given a host-owned, normalized record of
the commitments expressed by a successor snapshot, does that record preserve
one of the frozen case profiles?

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


class BasisScope(str, Enum):
    FIRST_TURN = "first_turn"
    WHOLE_DIALOGUE = "whole_dialogue"


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
    """Versioned criteria for one bounded transition and host target."""

    basis_id: str
    version: int
    case_id: str
    target_id: str
    question_id: str
    scope: BasisScope
    available_answer_ids: tuple[str, ...]
    relation: BindingRelation
    criteria: tuple[BasisCriterion, ...]

    def __post_init__(self) -> None:
        for field_name in ("basis_id", "case_id", "target_id", "question_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Basis field {field_name!r} must be non-empty.")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Basis version must be a positive integer.")
        if not isinstance(self.relation, BindingRelation):
            raise ValueError("Basis relation must be a BindingRelation.")
        if not isinstance(self.scope, BasisScope):
            raise ValueError("Basis scope must be a BasisScope.")
        if (
            not isinstance(self.available_answer_ids, tuple)
            or not self.available_answer_ids
            or any(not isinstance(answer_id, str) or not answer_id.strip() for answer_id in self.available_answer_ids)
            or len(set(self.available_answer_ids)) != len(self.available_answer_ids)
        ):
            raise ValueError("Basis available_answer_ids must be a unique non-empty tuple of strings.")
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
            "question_id": self.question_id,
            "scope": self.scope.value,
            "available_answer_ids": list(self.available_answer_ids),
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
    question_id: str
    answer_ids: tuple[str, ...]
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
    required = {"case_id", "target_id", "question_id", "answer_ids", "relation", "commitments"}
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
    answer_ids = payload["answer_ids"]
    if (
        not isinstance(answer_ids, list)
        or not answer_ids
        or any(not isinstance(answer_id, str) or not answer_id.strip() for answer_id in answer_ids)
        or len(set(answer_ids)) != len(answer_ids)
    ):
        raise BasisSchemaError("Profile evidence answer_ids must be a unique non-empty list of strings.")
    try:
        relation = BindingRelation(payload["relation"])
    except (TypeError, ValueError) as exc:
        raise BasisSchemaError("Profile evidence relation is unsupported.") from exc
    for field in ("case_id", "target_id", "question_id"):
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise BasisSchemaError(f"Profile evidence field {field!r} must be non-empty.")
    return ProfileAdjudicationEvidence(
        case_id=payload["case_id"],
        target_id=payload["target_id"],
        question_id=payload["question_id"],
        answer_ids=tuple(answer_ids),
        relation=relation,
        commitments=values,
    )


def _typed_evidence_errors(evidence: ProfileAdjudicationEvidence) -> tuple[str, ...]:
    errors: list[str] = []
    for field in ("case_id", "target_id", "question_id"):
        value = getattr(evidence, field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Profile evidence field {field!r} must be non-empty.")
    if not isinstance(evidence.relation, BindingRelation):
        errors.append("Profile evidence relation must be a BindingRelation.")
    answer_ids = evidence.answer_ids
    if (
        not isinstance(answer_ids, tuple)
        or not answer_ids
        or any(not isinstance(answer_id, str) or not answer_id.strip() for answer_id in answer_ids)
        or len(set(answer_ids)) != len(answer_ids)
    ):
        errors.append("Profile evidence answer_ids must be a unique non-empty tuple of strings.")
    commitments = evidence.commitments
    if not isinstance(commitments, Mapping):
        errors.append("Profile evidence commitments must be a mapping.")
    else:
        for key, value in commitments.items():
            if not isinstance(key, str) or not key.strip():
                errors.append("Profile evidence commitment keys must be non-empty strings.")
            if not isinstance(value, CommitmentState):
                errors.append(f"Profile evidence commitment {key!r} is not normalized.")
    return tuple(errors)


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
    typed_errors = _typed_evidence_errors(evidence)
    if typed_errors:
        return _not_comparable(
            basis=basis,
            evidence=evidence,
            schema=CheckStatus.INVALID,
            comparability=CheckStatus.NOT_APPLICABLE,
            errors=typed_errors,
        )
    if (
        evidence.case_id != basis.case_id
        or evidence.target_id != basis.target_id
        or evidence.question_id != basis.question_id
        or evidence.answer_ids != basis.available_answer_ids
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
    unknown = [key for key in evidence.commitments if key not in criterion_keys]
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


GENOME_IDENTITY_FIRST_TURN_BASIS = ProfileRelativeAdjudicationBasis(
    basis_id="genome-identity-first-turn",
    version=1,
    case_id="genome-identity-bounded",
    target_id="ambiguity-genome",
    question_id="meaning:ambiguity-genome",
    scope=BasisScope.FIRST_TURN,
    available_answer_ids=("genome-2",),
    relation=BindingRelation.ANCHORED_UPDATE,
    criteria=(
        BasisCriterion("identity_criterion_is_numerical", CommitmentState.AFFIRMED),
    ),
)


GENOME_IDENTITY_WHOLE_DIALOGUE_BASIS = ProfileRelativeAdjudicationBasis(
    basis_id="genome-identity-whole-dialogue",
    version=1,
    case_id="genome-identity-bounded",
    target_id="ambiguity-criterion",
    question_id="meaning:ambiguity-criterion",
    scope=BasisScope.WHOLE_DIALOGUE,
    available_answer_ids=("genome-2", "genome-4"),
    relation=BindingRelation.CREATE,
    criteria=(
        BasisCriterion("shared_genome_is_not_sufficient", CommitmentState.AFFIRMED),
        BasisCriterion("distinct_persons_can_share_genome", CommitmentState.AFFIRMED),
    ),
)


INTRINSIC_TIME_FIRST_TURN_BASIS = ProfileRelativeAdjudicationBasis(
    basis_id="intrinsic-time-first-turn",
    version=1,
    case_id="intrinsic-time-bounded",
    target_id="ambiguity-present",
    question_id="meaning:ambiguity-present",
    scope=BasisScope.FIRST_TURN,
    available_answer_ids=("time-2",),
    relation=BindingRelation.ANCHORED_UPDATE,
    criteria=(
        BasisCriterion("present_is_observer_independent", CommitmentState.AFFIRMED),
    ),
)


INTRINSIC_TIME_WHOLE_DIALOGUE_BASIS = ProfileRelativeAdjudicationBasis(
    basis_id="intrinsic-time-whole-dialogue",
    version=1,
    case_id="intrinsic-time-bounded",
    target_id="ambiguity-observer",
    question_id="ontology:ambiguity-observer",
    scope=BasisScope.WHOLE_DIALOGUE,
    available_answer_ids=("time-2", "time-4"),
    relation=BindingRelation.ANCHORED_UPDATE,
    criteria=(
        BasisCriterion("present_is_observer_independent", CommitmentState.AFFIRMED),
        BasisCriterion("sequence_order_alone_is_not_the_present", CommitmentState.AFFIRMED),
    ),
)


GENOME_IDENTITY_BASIS = GENOME_IDENTITY_FIRST_TURN_BASIS
INTRINSIC_TIME_BASIS = INTRINSIC_TIME_FIRST_TURN_BASIS


PROFILE_RELATIVE_BASES = {
    basis.basis_id: basis
    for basis in (
        GENOME_IDENTITY_FIRST_TURN_BASIS,
        GENOME_IDENTITY_WHOLE_DIALOGUE_BASIS,
        INTRINSIC_TIME_FIRST_TURN_BASIS,
        INTRINSIC_TIME_WHOLE_DIALOGUE_BASIS,
    )
}


__all__ = [
    "BasisCriterion",
    "BasisSchemaError",
    "BasisScope",
    "CommitmentState",
    "GENOME_IDENTITY_BASIS",
    "GENOME_IDENTITY_FIRST_TURN_BASIS",
    "GENOME_IDENTITY_WHOLE_DIALOGUE_BASIS",
    "INTRINSIC_TIME_BASIS",
    "INTRINSIC_TIME_FIRST_TURN_BASIS",
    "INTRINSIC_TIME_WHOLE_DIALOGUE_BASIS",
    "PROFILE_RELATIVE_BASES",
    "ProfileAdjudicationEvaluation",
    "ProfileAdjudicationEvidence",
    "ProfileRelativeAdjudicationBasis",
    "evaluate_profile_basis",
    "parse_profile_evidence",
]
