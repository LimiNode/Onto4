"""Deterministic, host-owned semantic verification research protocol.

This module deliberately does not create admission or adjudication receipts.
It compares an independently prepared expectation with a host-normalized
observation and ignores any provider self-report about correctness.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


PROTOCOL_VERSION = "pr60-independent-semantic-verification-v1"
SOURCE_SHA = "26cbe6a"


class SemanticStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNVERIFIED = "unverified"
    NOT_COMPARABLE = "not_comparable"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    OMITTED = "omitted"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class SemanticExpectation:
    target_key: str
    target_id: str
    required_evidence: tuple[str, ...]


@dataclass(frozen=True)
class ObservedSemanticSnapshot:
    """Host-normalized observation; provider claims are not represented."""

    target_key: str | None
    target_id: str | None
    resolution: ResolutionStatus
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    semantic_alignment: SemanticStatus
    literal_id_retention: bool | None
    ambiguity_resolution: SemanticStatus
    reason: str


def verify_independent(
    expected: SemanticExpectation,
    observed: ObservedSemanticSnapshot,
    *,
    provider_claim: Any = None,
) -> VerificationResult:
    """Evaluate host-owned evidence without trusting ``provider_claim``."""

    del provider_claim
    if not expected.target_key or not expected.target_id:
        return VerificationResult(
            SemanticStatus.NOT_COMPARABLE,
            None,
            SemanticStatus.NOT_COMPARABLE,
            "expectation is incomplete",
        )
    if observed.target_key is None:
        return VerificationResult(
            SemanticStatus.UNVERIFIED,
            None,
            SemanticStatus.UNVERIFIED,
            "observed semantic target is absent",
        )
    alignment = (
        SemanticStatus.CORRECT
        if observed.target_key == expected.target_key
        else SemanticStatus.INCORRECT
    )
    literal = observed.target_id == expected.target_id if observed.target_id is not None else None
    if alignment is not SemanticStatus.CORRECT:
        resolution = SemanticStatus.INCORRECT
        reason = "observed semantic target differs from the frozen expectation"
    elif observed.resolution is ResolutionStatus.RESOLVED:
        missing = set(expected.required_evidence) - set(observed.evidence)
        resolution = SemanticStatus.CORRECT if not missing else SemanticStatus.UNVERIFIED
        reason = "resolved with independent evidence" if not missing else "resolution evidence is incomplete"
    elif observed.resolution is ResolutionStatus.OMITTED:
        resolution = SemanticStatus.UNVERIFIED
        reason = "ambiguity omitted without evidence of resolution"
    else:
        resolution = SemanticStatus.UNVERIFIED
        reason = "ambiguity resolution is indeterminate"
    return VerificationResult(alignment, literal, resolution, reason)


def fixture_matrix() -> tuple[dict[str, Any], ...]:
    expected = SemanticExpectation("genome_identity", "target-a", ("identity-criterion",))
    return (
        {"name": "same_semantics_same_id", "expected": expected, "observed": ObservedSemanticSnapshot("genome_identity", "target-a", ResolutionStatus.RESOLVED, ("identity-criterion",))},
        {"name": "same_semantics_different_id", "expected": expected, "observed": ObservedSemanticSnapshot("genome_identity", "target-b", ResolutionStatus.RESOLVED, ("identity-criterion",))},
        {"name": "wrong_semantics_correct_id", "expected": expected, "observed": ObservedSemanticSnapshot("numerical_count", "target-a", ResolutionStatus.RESOLVED, ("identity-criterion",))},
        {"name": "ambiguity_genuinely_resolved", "expected": expected, "observed": ObservedSemanticSnapshot("genome_identity", "target-a", ResolutionStatus.RESOLVED, ("identity-criterion",))},
        {"name": "ambiguity_merely_omitted", "expected": expected, "observed": ObservedSemanticSnapshot("genome_identity", "target-a", ResolutionStatus.OMITTED)},
        {"name": "semantic_relationship_indeterminate", "expected": expected, "observed": ObservedSemanticSnapshot("genome_identity", "target-a", ResolutionStatus.INDETERMINATE)},
    )


def run_offline_protocol() -> dict[str, Any]:
    rows = []
    for fixture in fixture_matrix():
        result = verify_independent(fixture["expected"], fixture["observed"], provider_claim={"semantic": "self-reported"})
        rows.append({
            "fixture": fixture["name"],
            "semantic_alignment": result.semantic_alignment.value,
            "literal_id_retention": result.literal_id_retention,
            "ambiguity_resolution": result.ambiguity_resolution.value,
            "reason": result.reason,
        })
    return {
        "record_type": "pr60_independent_semantic_verification_protocol",
        "protocol_version": PROTOCOL_VERSION,
        "source_sha": SOURCE_SHA,
        "rows": rows,
        "semantic_adjudication_receipt_created": False,
        "production_admission_changed": False,
    }
