"""Deterministic, host-owned semantic verification research protocol.

This module deliberately does not create admission or adjudication receipts.
It compares an independently prepared expectation with a host-normalized
observation and ignores any provider self-report about correctness.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any


PROTOCOL_VERSION = "pr60-independent-semantic-verification-v1"
SOURCE_SHA = "dd7be787408090ae5b7e5a381c0dbb406cc94648"


class SemanticStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNVERIFIED = "unverified"
    NOT_COMPARABLE = "not_comparable"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    OMITTED = "omitted"
    INDETERMINATE = "indeterminate"


class EvidenceAuthority(str, Enum):
    HOST_INDEPENDENT = "host_independent"
    PROVIDER = "provider"
    UNKNOWN = "unknown"


class EvidenceStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONTRADICTORY = "contradictory"


class VerificationMode(str, Enum):
    REAL_OBSERVATION = "real_observation"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


@dataclass(frozen=True)
class EvidenceReference:
    source_id: str
    authority: EvidenceAuthority
    status: EvidenceStatus
    statement_key: str


@dataclass(frozen=True)
class ObservationProvenance:
    observation_id: str
    normalizer_id: str
    normalizer_version: str
    source_id: str
    authority: EvidenceAuthority


@dataclass(frozen=True)
class HostEvidenceAttestation:
    """Frozen host-owned relationship absent from a provider observation."""

    expectation_target_key: str
    observation_id: str
    normalizer_id: str
    normalizer_version: str
    observation_source_id: str
    evidence_source_ids: tuple[str, ...]
    evidence_statement_keys: tuple[str, ...]
    observation_digest: str


def _observation_digest(
    expected: "SemanticExpectation",
    observed: "ObservedSemanticSnapshot",
) -> str:
    """Return a canonical host-owned fingerprint of the bound observation."""

    provenance = observed.provenance
    payload = {
        "expected": {
            "target_key": expected.target_key,
            "target_id": expected.target_id,
            "required_evidence": list(expected.required_evidence),
        },
        "observed": {
            "target_key": observed.target_key,
            "target_id": observed.target_id,
            "resolution": observed.resolution.value,
            "provenance": None
            if provenance is None
            else {
                "observation_id": provenance.observation_id,
                "normalizer_id": provenance.normalizer_id,
                "normalizer_version": provenance.normalizer_version,
                "source_id": provenance.source_id,
                "authority": provenance.authority.value,
            },
            "evidence": [
                {
                    "source_id": evidence.source_id,
                    "authority": evidence.authority.value,
                    "status": evidence.status.value,
                    "statement_key": evidence.statement_key,
                }
                for evidence in observed.evidence
            ],
        },
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class TrustedHostEvidenceResolver:
    """Resolve only relationships in an independently maintained reference set."""

    attestations: frozenset[HostEvidenceAttestation]

    def verifies(
        self,
        expected: "SemanticExpectation",
        observed: "ObservedSemanticSnapshot",
    ) -> bool:
        provenance = observed.provenance
        if provenance is None:
            return False
        candidate = HostEvidenceAttestation(
            expected.target_key,
            provenance.observation_id,
            provenance.normalizer_id,
            provenance.normalizer_version,
            provenance.source_id,
            tuple(evidence.source_id for evidence in observed.evidence),
            tuple(evidence.statement_key for evidence in observed.evidence),
            _observation_digest(expected, observed),
        )
        return candidate in self.attestations


@dataclass(frozen=True)
class SemanticExpectation:
    target_key: str
    target_id: str
    required_evidence: tuple[str, ...]


@dataclass(frozen=True)
class ObservedSemanticSnapshot:
    """Observation plus an auditable provenance boundary."""

    target_key: str | None
    target_id: str | None
    resolution: ResolutionStatus
    evidence: tuple[EvidenceReference, ...] = ()
    provenance: ObservationProvenance | None = None


@dataclass(frozen=True)
class VerificationResult:
    semantic_alignment: SemanticStatus
    literal_id_retention: bool | None
    ambiguity_resolution: SemanticStatus
    reason: str
    result_scope: str = "unverified"


def verify_independent(
    expected: SemanticExpectation,
    observed: ObservedSemanticSnapshot,
    *,
    provider_claim: Any = None,
    mode: VerificationMode = VerificationMode.REAL_OBSERVATION,
    resolver: TrustedHostEvidenceResolver | None = None,
) -> VerificationResult:
    """Evaluate host-owned evidence without trusting ``provider_claim``."""

    del provider_claim
    if not isinstance(mode, VerificationMode):
        return VerificationResult(
            SemanticStatus.UNVERIFIED,
            None,
            SemanticStatus.UNVERIFIED,
            "verification mode is invalid",
        )
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
    provenance = observed.provenance
    if provenance is None or not all(
        (provenance.observation_id, provenance.normalizer_id, provenance.normalizer_version, provenance.source_id)
    ) or provenance.authority is not EvidenceAuthority.HOST_INDEPENDENT:
        return VerificationResult(
            SemanticStatus.UNVERIFIED,
            None,
            SemanticStatus.UNVERIFIED,
            "observation lacks verified independent provenance",
        )
    if any(evidence.status is EvidenceStatus.CONTRADICTORY for evidence in observed.evidence):
        return VerificationResult(
            SemanticStatus.UNVERIFIED,
            None,
            SemanticStatus.UNVERIFIED,
            "evidence is contradictory",
        )
    if not observed.evidence or any(
        evidence.authority is not EvidenceAuthority.HOST_INDEPENDENT
        or evidence.status is not EvidenceStatus.VERIFIED
        for evidence in observed.evidence
    ):
        return VerificationResult(
            SemanticStatus.UNVERIFIED,
            None,
            SemanticStatus.UNVERIFIED,
            "evidence is absent or not independently verified",
        )
    if len({evidence.source_id for evidence in observed.evidence}) != len(observed.evidence):
        return VerificationResult(
            SemanticStatus.UNVERIFIED,
            None,
            SemanticStatus.UNVERIFIED,
            "evidence sources are not independently distinct",
        )
    if mode is VerificationMode.REAL_OBSERVATION and (
        resolver is None or not resolver.verifies(expected, observed)
    ):
        return VerificationResult(
            SemanticStatus.UNVERIFIED,
            None,
            SemanticStatus.UNVERIFIED,
            "trusted host evidence resolver did not attest the observation binding",
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
        available = {evidence.statement_key for evidence in observed.evidence}
        missing = set(expected.required_evidence) - available
        resolution = SemanticStatus.CORRECT if not missing else SemanticStatus.UNVERIFIED
        reason = "resolved with independent evidence" if not missing else "resolution evidence is incomplete"
    elif observed.resolution is ResolutionStatus.OMITTED:
        resolution = SemanticStatus.UNVERIFIED
        reason = "ambiguity omitted without evidence of resolution"
    else:
        resolution = SemanticStatus.UNVERIFIED
        reason = "ambiguity resolution is indeterminate"
    scope = (
        "synthetic_oracle_fixture"
        if mode is VerificationMode.SYNTHETIC_FIXTURE
        else "trusted_host_evidence"
    )
    return VerificationResult(alignment, literal, resolution, reason, scope)


def fixture_matrix() -> tuple[dict[str, Any], ...]:
    expected = SemanticExpectation("genome_identity", "target-a", ("identity-criterion",))
    provenance = ObservationProvenance("observation-1", "host-normalizer", "v1", "evidence-a", EvidenceAuthority.HOST_INDEPENDENT)
    evidence = (EvidenceReference("evidence-a", EvidenceAuthority.HOST_INDEPENDENT, EvidenceStatus.VERIFIED, "identity-criterion"),)
    def observed(key: str | None, target_id: str | None, resolution: ResolutionStatus, *, verified: bool = True, source: str = "evidence-a", normalizer: str = "host-normalizer", contradictory: bool = False, duplicate_source: bool = False) -> ObservedSemanticSnapshot:
        local_provenance = ObservationProvenance("observation-1", normalizer, "v1", source, EvidenceAuthority.HOST_INDEPENDENT) if verified else None
        local_evidence = (
            EvidenceReference(source, EvidenceAuthority.HOST_INDEPENDENT, EvidenceStatus.CONTRADICTORY if contradictory else EvidenceStatus.VERIFIED, "identity-criterion"),
        ) if verified else ()
        if duplicate_source:
            local_evidence = local_evidence + local_evidence
        return ObservedSemanticSnapshot(
            key,
            target_id,
            resolution,
            local_evidence,
            local_provenance,
        )
    return (
        {"name": "same_semantics_same_id", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.RESOLVED)},
        {"name": "same_semantics_different_id", "expected": expected, "observed": observed("genome_identity", "target-b", ResolutionStatus.RESOLVED)},
        {"name": "wrong_semantics_correct_id", "expected": expected, "observed": observed("numerical_count", "target-a", ResolutionStatus.RESOLVED)},
        {"name": "ambiguity_genuinely_resolved", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.RESOLVED)},
        {"name": "ambiguity_merely_omitted", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.OMITTED)},
        {"name": "semantic_relationship_indeterminate", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.INDETERMINATE)},
        {"name": "untrusted_observation", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.RESOLVED, verified=False)},
        {"name": "provider_self_report_without_evidence", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.RESOLVED, verified=False)},
        {"name": "missing_normalizer_provenance", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.RESOLVED, normalizer="")},
        {"name": "duplicate_evidence_source", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.RESOLVED, duplicate_source=True)},
        {"name": "contradictory_evidence", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.RESOLVED, contradictory=True)},
        {"name": "apparent_resolution_without_evidence", "expected": expected, "observed": observed("genome_identity", "target-a", ResolutionStatus.RESOLVED, verified=False)},
    )


def run_offline_protocol() -> dict[str, Any]:
    rows = []
    for fixture in fixture_matrix():
        result = verify_independent(
            fixture["expected"],
            fixture["observed"],
            provider_claim={"semantic": "self-reported"},
            mode=VerificationMode.SYNTHETIC_FIXTURE,
        )
        rows.append({
            "fixture": fixture["name"],
            "semantic_alignment": result.semantic_alignment.value,
            "literal_id_retention": result.literal_id_retention,
            "ambiguity_resolution": result.ambiguity_resolution.value,
            "reason": result.reason,
            "result_scope": result.result_scope,
            "synthetic_oracle_fixture": True,
        })
    return {
        "record_type": "pr60_independent_semantic_verification_protocol",
        "protocol_version": PROTOCOL_VERSION,
        "source_sha": SOURCE_SHA,
        "rows": rows,
        "semantic_adjudication_receipt_created": False,
        "production_admission_changed": False,
    }
