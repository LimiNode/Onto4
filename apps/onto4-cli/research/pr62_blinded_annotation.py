"""Minimal blinded annotation and host-evidence boundary for PR #62.

The tool emits reviewer-safe packets and immutable annotation records. It is
not an annotation service, a semantic adjudicator or a source of production
authority. Provider payloads cannot create host attestations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable


PROTOCOL_VERSION = "pr62-blinded-annotation-v2"
RUBRIC_VERSION = "pr61-rubric-v2"
PACKET_VERSION = "pr62-packet-v2"
REGISTRY_VERSION = "pr62-host-registry-v1"


class VerificationStage(str, Enum):
    RECEIVED = "received"
    SOURCE_VERIFIED = "source_verified"
    NORMALIZER_VERIFIED = "normalizer_verified"
    OBSERVATION_MATCHED = "observation_matched"
    EVIDENCE_VERIFIED = "evidence_verified"
    ATTESTED = "attested"


class AnnotationKind(str, Enum):
    CANDIDATE = "candidate_annotation"
    INDEPENDENT = "independent_annotation"
    ADJUDICATED = "adjudicated_annotation"


_ALIGNMENTS = {"aligned", "misaligned", "indeterminate"}
_RESOLUTIONS = {"resolved", "not_resolved", "merely_omitted", "indeterminate"}
_EVIDENCE = {"sufficient", "insufficient", "contradictory", "not_available"}
_ALIAS = re.compile(r"^[A-Za-z0-9_-]+$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _packet_content_digest(packet: "BlindedPacket") -> str:
    return hashlib.sha256(_canonical(packet.content_payload())).hexdigest()


def _semantic_description(case: Any) -> str:
    if case.family == "genome_identity":
        return (
            "The ambiguity concerns whether sharing a genome establishes numerical "
            "identity, distinct from genetic similarity or ancestry."
        )
    if case.family == "intrinsic_time":
        return (
            "The ambiguity concerns whether a present belongs intrinsically to the "
            "sequence, distinct from observer-relative coordinate time."
        )
    raise ValueError("unsupported case family for blinded packet")


@dataclass(frozen=True)
class BlindedPacket:
    packet_id: str
    case_alias: str
    rubric_version: str
    packet_version: str
    initial_interpretation: str
    clarification_question: str
    intended_target_description: str
    proposed_successor: str
    neutral_target_alias: str
    content_digest: str

    def content_payload(self) -> dict[str, Any]:
        return {
            "case_alias": self.case_alias,
            "rubric_version": self.rubric_version,
            "packet_version": self.packet_version,
            "initial_interpretation": self.initial_interpretation,
            "clarification_question": self.clarification_question,
            "intended_target_description": self.intended_target_description,
            "proposed_successor": self.proposed_successor,
            "neutral_target_alias": self.neutral_target_alias,
        }

    def public_dict(self) -> dict[str, Any]:
        return {"packet_id": self.packet_id, **self.content_payload(), "content_digest": self.content_digest}


def make_blinded_packet(
    case: Any,
    *,
    condition: str | None = None,
    model_name: str | None = None,
    target_id: str | None = None,
) -> BlindedPacket:
    """Create a content-bound packet while discarding technical condition data."""

    del condition, model_name, target_id
    description = _semantic_description(case)
    content = {
        "case_alias": "case-under-review",
        "rubric_version": RUBRIC_VERSION,
        "packet_version": PACKET_VERSION,
        "initial_interpretation": case.initial_interpretation,
        "clarification_question": case.clarification_question,
        "intended_target_description": description,
        "proposed_successor": case.proposed_successor,
        "neutral_target_alias": "target-under-review",
    }
    digest = hashlib.sha256(_canonical(content)).hexdigest()
    packet_id = "packet-" + hashlib.sha256((case.case_id + ":" + digest).encode()).hexdigest()[:16]
    return BlindedPacket(
        packet_id,
        packet_id,
        RUBRIC_VERSION,
        PACKET_VERSION,
        case.initial_interpretation,
        case.clarification_question,
        description,
        case.proposed_successor,
        "target-under-review",
        hashlib.sha256(_canonical({**content, "case_alias": packet_id})).hexdigest(),
    )


@dataclass(frozen=True)
class AnnotationRecord:
    reviewer_alias: str
    case_alias: str
    packet_content_digest: str
    rubric_version: str
    packet_version: str
    semantic_alignment: str
    ambiguity_resolution: str
    evidence_sufficiency: str
    confidence: float
    rationale_span_refs: tuple[str, ...] = ()
    abstained: bool = False
    abstention_reason: str | None = None
    annotation_kind: AnnotationKind = AnnotationKind.CANDIDATE

    def validate(self, packet: BlindedPacket) -> None:
        if packet.content_digest != _packet_content_digest(packet):
            raise ValueError("packet content digest does not match packet content")
        if not _ALIAS.fullmatch(self.reviewer_alias) or not _ALIAS.fullmatch(self.case_alias):
            raise ValueError("reviewer and case aliases must be redaction-safe")
        if self.case_alias != packet.case_alias:
            raise ValueError("annotation case does not match blinded packet")
        if self.packet_content_digest != packet.content_digest:
            raise ValueError("annotation is bound to different packet content")
        if self.rubric_version != packet.rubric_version or self.packet_version != packet.packet_version:
            raise ValueError("annotation version does not match packet")
        if self.semantic_alignment not in _ALIGNMENTS:
            raise ValueError("invalid semantic alignment")
        if self.ambiguity_resolution not in _RESOLUTIONS:
            raise ValueError("invalid ambiguity resolution")
        if self.evidence_sufficiency not in _EVIDENCE:
            raise ValueError("invalid evidence sufficiency")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        if len(set(self.rationale_span_refs)) != len(self.rationale_span_refs):
            raise ValueError("rationale span references must be unique")
        if self.abstained and not (self.abstention_reason or "").strip():
            raise ValueError("abstention requires a reason")

    def private_dict(self) -> dict[str, Any]:
        return {
            "record_type": "pr62_blinded_annotation",
            "reviewer_alias": self.reviewer_alias,
            "case_alias": self.case_alias,
            "packet_content_digest": self.packet_content_digest,
            "rubric_version": self.rubric_version,
            "packet_version": self.packet_version,
            "semantic_alignment": self.semantic_alignment,
            "ambiguity_resolution": self.ambiguity_resolution,
            "evidence_sufficiency": self.evidence_sufficiency,
            "confidence": self.confidence,
            "rationale_span_refs": list(self.rationale_span_refs),
            "abstained": self.abstained,
            "abstention_reason": self.abstention_reason,
            "annotation_kind": self.annotation_kind.value,
        }

    def public_dict(self) -> dict[str, Any]:
        """Return only the categorical, redaction-safe representation."""

        return {
            "record_type": "pr62_blinded_annotation_public",
            "reviewer_alias": self.reviewer_alias,
            "case_alias": self.case_alias,
            "packet_content_digest": self.packet_content_digest,
            "rubric_version": self.rubric_version,
            "packet_version": self.packet_version,
            "semantic_alignment": self.semantic_alignment,
            "ambiguity_resolution": self.ambiguity_resolution,
            "evidence_sufficiency": self.evidence_sufficiency,
            "confidence": self.confidence,
            "abstained": self.abstained,
            "annotation_kind": self.annotation_kind.value,
        }


@dataclass(frozen=True)
class ReviewerIdentity:
    reviewer_alias: str
    identity_key: str
    independent: bool
    approved: bool = True


@dataclass(frozen=True)
class PacketAssignment:
    packet_id: str
    packet_content_digest: str
    reviewer_alias: str


@dataclass(frozen=True)
class VerifiedEvidenceRecord:
    packet_id: str
    packet_content_digest: str
    reviewer_alias: str
    annotation_digest: str
    rubric_version: str
    source_id: str
    normalizer_id: str
    normalizer_version: str
    verified: bool


@dataclass(frozen=True)
class RegistryAttestation:
    """Separate host attestation required before registry data can gate live work."""

    registry_id: str
    source_id: str
    evidence_digest: str
    verified: bool = True
    registry_version: str = REGISTRY_VERSION
    registry_digest: str = ""


@dataclass(frozen=True)
class HostRegistry:
    """Separately maintained research registry, not provider-supplied data."""

    registry_id: str
    reviewers: tuple[ReviewerIdentity, ...]
    assignments: tuple[PacketAssignment, ...]
    evidence: tuple[VerifiedEvidenceRecord, ...]
    host_controlled: bool = True
    registry_attestation: RegistryAttestation | None = None

    def snapshot_payload(self) -> dict[str, Any]:
        """Canonical identity of every registry binding used by evaluation."""

        return {
            "registry_id": self.registry_id,
            "registry_version": REGISTRY_VERSION,
            "host_controlled": self.host_controlled,
            "reviewers": [
                {
                    "reviewer_alias": reviewer.reviewer_alias,
                    "identity_key": reviewer.identity_key,
                    "independent": reviewer.independent,
                    "approved": reviewer.approved,
                }
                for reviewer in self.reviewers
            ],
            "assignments": [
                {
                    "packet_id": assignment.packet_id,
                    "packet_content_digest": assignment.packet_content_digest,
                    "reviewer_alias": assignment.reviewer_alias,
                }
                for assignment in self.assignments
            ],
            "evidence": [
                {
                    "packet_id": evidence.packet_id,
                    "packet_content_digest": evidence.packet_content_digest,
                    "reviewer_alias": evidence.reviewer_alias,
                    "annotation_digest": evidence.annotation_digest,
                    "rubric_version": evidence.rubric_version,
                    "source_id": evidence.source_id,
                    "normalizer_id": evidence.normalizer_id,
                    "normalizer_version": evidence.normalizer_version,
                    "verified": evidence.verified,
                }
                for evidence in self.evidence
            ],
        }

    def snapshot_digest(self) -> str:
        return hashlib.sha256(_canonical(self.snapshot_payload())).hexdigest()

    def trusted_for_live_evaluation(self, trusted_source: Any | None = None) -> bool:
        attestation = self.registry_attestation
        if trusted_source is None:
            return False
        verifier = getattr(trusted_source, "verify_registry", None)
        if verifier is None:
            return False
        structurally_valid = bool(
            self.host_controlled
            and attestation is not None
            and attestation.verified
            and attestation.registry_id == self.registry_id
            and attestation.registry_version == REGISTRY_VERSION
            and attestation.registry_digest == self.snapshot_digest()
            and attestation.source_id
            and len(attestation.evidence_digest) == 64
            and all(character in "0123456789abcdef" for character in attestation.evidence_digest.lower())
        )
        if not structurally_valid:
            return False
        try:
            return bool(verifier(attestation, self, self.snapshot_digest()))
        except Exception:
            return False

    def verify(self, packet: BlindedPacket, annotation: AnnotationRecord, record: "HostVerificationRecord") -> bool:
        if not self.host_controlled or annotation.annotation_kind is not AnnotationKind.INDEPENDENT:
            return False
        identities = [reviewer for reviewer in self.reviewers if reviewer.reviewer_alias == record.reviewer_alias]
        if len(identities) != 1 or not identities[0].independent or not identities[0].approved:
            return False
        if len({reviewer.identity_key for reviewer in self.reviewers}) != len(self.reviewers):
            return False
        if not any(
            assignment.packet_id == packet.packet_id
            and assignment.packet_content_digest == packet.content_digest
            and assignment.reviewer_alias == record.reviewer_alias
            for assignment in self.assignments
        ):
            return False
        digest = annotation_digest(annotation)
        return any(
            evidence.packet_id == packet.packet_id
            and evidence.packet_content_digest == packet.content_digest
            and evidence.reviewer_alias == record.reviewer_alias
            and evidence.annotation_digest == digest
            and evidence.rubric_version == packet.rubric_version
            and evidence.source_id == record.source_id
            and evidence.normalizer_id == record.normalizer_id
            and evidence.normalizer_version == record.normalizer_version
            and evidence.verified
            for evidence in self.evidence
        )

    def independent_reviewer_count(self) -> int:
        independent = [reviewer for reviewer in self.reviewers if reviewer.independent and reviewer.approved]
        keys = {reviewer.identity_key for reviewer in independent}
        return len(keys) if len(keys) == len(independent) else 0


@dataclass(frozen=True)
class HostVerificationRecord:
    packet_id: str
    packet_content_digest: str
    annotation_digest: str
    rubric_version: str
    reviewer_alias: str
    source_id: str
    normalizer_id: str
    normalizer_version: str
    stage: VerificationStage
    independent_basis: str
    provider_payload_used: bool = False


@dataclass(frozen=True)
class AnnotationAttestation:
    packet_id: str
    packet_content_digest: str
    annotation_digest: str
    reviewer_alias: str
    rubric_version: str
    source_id: str
    normalizer_id: str
    normalizer_version: str


def annotation_digest(annotation: AnnotationRecord) -> str:
    return hashlib.sha256(_canonical(annotation.private_dict())).hexdigest()


def attest_host_annotation(
    record: HostVerificationRecord,
    *,
    packet: BlindedPacket,
    annotation: AnnotationRecord,
    registry: HostRegistry,
) -> AnnotationAttestation:
    """Attest only an annotation present in the independently maintained registry."""

    if record.provider_payload_used:
        raise ValueError("provider payload cannot create host attestation")
    if record.stage is not VerificationStage.EVIDENCE_VERIFIED:
        raise ValueError("host evidence must be verified before attestation")
    if not all((record.independent_basis, record.source_id, record.normalizer_id, record.normalizer_version)):
        raise ValueError("host verification provenance is incomplete")
    annotation.validate(packet)
    digest = annotation_digest(annotation)
    if digest != record.annotation_digest or record.packet_id != packet.packet_id or record.packet_content_digest != packet.content_digest:
        raise ValueError("verification record does not bind exact packet and annotation")
    if record.rubric_version != packet.rubric_version or record.reviewer_alias != annotation.reviewer_alias:
        raise ValueError("verification record provenance does not match annotation")
    if not registry.verify(packet, annotation, record):
        raise ValueError("host registry did not verify reviewer, assignment and evidence")
    return AnnotationAttestation(
        packet.packet_id,
        packet.content_digest,
        digest,
        annotation.reviewer_alias,
        packet.rubric_version,
        record.source_id,
        record.normalizer_id,
        record.normalizer_version,
    )


def compare_reviewers(records: Iterable[AnnotationRecord]) -> tuple[dict[str, Any], ...]:
    """Return a redaction-safe disagreement summary for public reports.

    Reviewer rationale, abstention explanations and span references remain
    private inputs.  They are deliberately not serialized at this boundary.
    """

    grouped: dict[str, list[AnnotationRecord]] = {}
    for record in records:
        if not _ALIAS.fullmatch(record.reviewer_alias) or not _ALIAS.fullmatch(record.case_alias):
            raise ValueError("public disagreement aliases must be redaction-safe")
        if record.semantic_alignment not in _ALIGNMENTS:
            raise ValueError("public disagreement contains invalid alignment")
        if record.ambiguity_resolution not in _RESOLUTIONS:
            raise ValueError("public disagreement contains invalid resolution")
        if record.evidence_sufficiency not in _EVIDENCE:
            raise ValueError("public disagreement contains invalid evidence status")
        grouped.setdefault(record.case_alias, []).append(record)
    summaries = []
    for case_alias, judgments in sorted(grouped.items()):
        alignments = {record.semantic_alignment for record in judgments}
        resolutions = {record.ambiguity_resolution for record in judgments}
        evidence = {record.evidence_sufficiency for record in judgments}
        summaries.append({
            "case_alias": case_alias,
            "reviewer_count": len(judgments),
            "reviewer_aliases": sorted(record.reviewer_alias for record in judgments),
            "semantic_alignment_labels": sorted(alignments),
            "ambiguity_resolution_labels": sorted(resolutions),
            "evidence_sufficiency_labels": sorted(evidence),
            "abstention_count": sum(record.abstained for record in judgments),
            "abstention_reason_codes": sorted({"abstained" if record.abstained else "not_abstained" for record in judgments}),
            "alignment_agreement": len(alignments) == 1,
            "resolution_agreement": len(resolutions) == 1,
            "evidence_agreement": len(evidence) == 1,
            "unresolved_disagreement": len(alignments) > 1 or len(resolutions) > 1 or len(evidence) > 1,
            "adjudicated": False,
        })
    return tuple(summaries)


def compare_reviewers_private(records: Iterable[AnnotationRecord]) -> tuple[dict[str, Any], ...]:
    """Keep full reviewer material in a private research boundary only."""

    grouped: dict[str, list[AnnotationRecord]] = {}
    for record in records:
        grouped.setdefault(record.case_alias, []).append(record)
    summaries = []
    for case_alias, judgments in sorted(grouped.items()):
        alignments = {record.semantic_alignment for record in judgments}
        resolutions = {record.ambiguity_resolution for record in judgments}
        evidence = {record.evidence_sufficiency for record in judgments}
        summaries.append({
            "case_alias": case_alias,
            "reviewer_count": len(judgments),
            "raw_judgments": [record.private_dict() for record in judgments],
            "alignment_agreement": len(alignments) == 1,
            "resolution_agreement": len(resolutions) == 1,
            "evidence_agreement": len(evidence) == 1,
            "unresolved_disagreement": len(alignments) > 1 or len(resolutions) > 1 or len(evidence) > 1,
            "adjudicated": False,
        })
    return tuple(summaries)
