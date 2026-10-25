"""Minimal blinded annotation and host-evidence boundary for PR #62.

The tool emits reviewer-safe packets and immutable annotation records.  It is
not an annotation service, a semantic adjudicator or a source of production
authority.  Provider payloads cannot create host attestations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable


PROTOCOL_VERSION = "pr62-blinded-annotation-v1"
RUBRIC_VERSION = "pr61-rubric-v1"
PACKET_VERSION = "pr62-packet-v1"


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


def _safe_alias(case_id: str) -> str:
    return "packet-" + hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:12]


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

    def public_dict(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "case_alias": self.case_alias,
            "rubric_version": self.rubric_version,
            "packet_version": self.packet_version,
            "initial_interpretation": self.initial_interpretation,
            "clarification_question": self.clarification_question,
            "intended_target_description": self.intended_target_description,
            "proposed_successor": self.proposed_successor,
            "neutral_target_alias": self.neutral_target_alias,
        }


def make_blinded_packet(case: Any, *, condition: str | None = None, model_name: str | None = None, target_id: str | None = None) -> BlindedPacket:
    """Create a packet while deliberately discarding technical condition data."""

    del condition, model_name, target_id
    packet_id = _safe_alias(case.case_id)
    return BlindedPacket(
        packet_id,
        packet_id,
        RUBRIC_VERSION,
        PACKET_VERSION,
        case.initial_interpretation,
        case.clarification_question,
        "The packet's intended semantic target, described without a technical identifier.",
        case.proposed_successor,
        "target-under-review",
    )


@dataclass(frozen=True)
class AnnotationRecord:
    reviewer_alias: str
    case_alias: str
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
        if not _ALIAS.fullmatch(self.reviewer_alias) or not _ALIAS.fullmatch(self.case_alias):
            raise ValueError("reviewer and case aliases must be redaction-safe")
        if self.case_alias != packet.case_alias:
            raise ValueError("annotation case does not match blinded packet")
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
        if self.annotation_kind is AnnotationKind.INDEPENDENT and self.reviewer_alias.startswith("candidate-"):
            raise ValueError("candidate alias cannot claim independent annotation")

    def public_dict(self) -> dict[str, Any]:
        return {
            "record_type": "pr62_blinded_annotation",
            "reviewer_alias": self.reviewer_alias,
            "case_alias": self.case_alias,
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


@dataclass(frozen=True)
class HostVerificationRecord:
    packet_id: str
    annotation_digest: str
    rubric_version: str
    source_id: str
    normalizer_id: str
    normalizer_version: str
    stage: VerificationStage
    independent_basis: str
    provider_payload_used: bool = False


@dataclass(frozen=True)
class AnnotationAttestation:
    packet_id: str
    annotation_digest: str
    rubric_version: str
    source_id: str
    normalizer_id: str
    normalizer_version: str


def annotation_digest(annotation: AnnotationRecord) -> str:
    payload = annotation.public_dict()
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def attest_host_annotation(record: HostVerificationRecord) -> AnnotationAttestation:
    """Create a research attestation only after host verification is complete."""

    if record.provider_payload_used:
        raise ValueError("provider payload cannot create host attestation")
    if record.stage is not VerificationStage.EVIDENCE_VERIFIED:
        raise ValueError("host evidence must be verified before attestation")
    if not all((record.packet_id, record.annotation_digest, record.rubric_version, record.source_id, record.normalizer_id, record.normalizer_version, record.independent_basis)):
        raise ValueError("host verification record is incomplete")
    return AnnotationAttestation(
        record.packet_id,
        record.annotation_digest,
        record.rubric_version,
        record.source_id,
        record.normalizer_id,
        record.normalizer_version,
    )


def compare_reviewers(records: Iterable[AnnotationRecord]) -> tuple[dict[str, Any], ...]:
    """Return raw disagreement summaries without majority-vote adjudication."""

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
            "raw_judgments": [record.public_dict() for record in judgments],
            "alignment_agreement": len(alignments) == 1,
            "resolution_agreement": len(resolutions) == 1,
            "evidence_agreement": len(evidence) == 1,
            "unresolved_disagreement": len(alignments) > 1 or len(resolutions) > 1 or len(evidence) > 1,
            "adjudicated": False,
        })
    return tuple(summaries)
