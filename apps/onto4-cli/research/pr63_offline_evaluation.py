"""Deterministic offline calibration and readiness gate for PR #63.

The runner composes frozen packets, submitted annotations and a separately
maintained host registry with the existing PR60 verifier. It reports readiness
and research-only outcomes; fixture labels are never promoted to semantic gold.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Iterable


PROTOCOL_VERSION = "pr63-offline-evaluation-v2"
READINESS_STATUS = "pending_independent_annotations"


def _load(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_PR60 = _load("pr60_independent_semantic_verification", "pr60_independent_semantic_verification.py")
_PR61 = _load("pr61_semantic_evaluation_protocol", "pr61_semantic_evaluation_protocol.py")
_PR62 = _load("pr62_blinded_annotation", "pr62_blinded_annotation.py")


@dataclass(frozen=True)
class OfflineCaseResult:
    case_id: str
    annotation_kind: str
    semantic_alignment: str
    ambiguity_resolution: str
    evidence_sufficiency: str
    verifier_status: str
    comparable: bool
    reason: str


def _trusted_resolver(expected, observed):
    provenance = observed.provenance
    assert provenance is not None
    attestation = _PR60.HostEvidenceAttestation(
        expected.target_key, provenance.observation_id, provenance.normalizer_id,
        provenance.normalizer_version, provenance.source_id,
        tuple(evidence.source_id for evidence in observed.evidence),
        tuple(evidence.statement_key for evidence in observed.evidence),
        _PR60._observation_digest(expected, observed),
    )
    return _PR60.TrustedHostEvidenceResolver(frozenset((attestation,)))


def _verified_observation(target_key: str = "x", target_id: str = "id-x", *, resolution=None):
    resolution = resolution or _PR60.ResolutionStatus.RESOLVED
    provenance = _PR60.ObservationProvenance("obs", "normalizer", "v1", "source", _PR60.EvidenceAuthority.HOST_INDEPENDENT)
    evidence = (_PR60.EvidenceReference("source", _PR60.EvidenceAuthority.HOST_INDEPENDENT, _PR60.EvidenceStatus.VERIFIED, "evidence"),)
    return _PR60.ObservedSemanticSnapshot(target_key, target_id, resolution, evidence, provenance)


def _control(name: str, condition: bool, detail: str) -> dict[str, Any]:
    return {"control": name, "passed": condition, "detail": detail}


def run_negative_controls() -> tuple[dict[str, Any], ...]:
    expected = _PR60.SemanticExpectation("x", "id-x", ("evidence",))
    observed = _verified_observation()
    resolver = _trusted_resolver(expected, observed)
    exact = _PR60.verify_independent(expected, observed, resolver=resolver)
    wrong_meaning_same_id = _PR60.verify_independent(
        expected, _verified_observation(target_key="other", target_id="id-x"), resolver=resolver
    )
    changed_id_same_meaning = _PR60.verify_independent(
        expected, _verified_observation(target_key="x", target_id="other"), resolver=resolver
    )
    omitted = _PR60.verify_independent(expected, _verified_observation(resolution=_PR60.ResolutionStatus.OMITTED), resolver=resolver)
    invalid_mode = _PR60.verify_independent(expected, observed, mode="real_observation", resolver=resolver)
    provider_only = _PR60.verify_independent(
        expected,
        _PR60.ObservedSemanticSnapshot(
            "x", "id-x", _PR60.ResolutionStatus.RESOLVED,
            (_PR60.EvidenceReference("provider", _PR60.EvidenceAuthority.PROVIDER, _PR60.EvidenceStatus.VERIFIED, "evidence"),),
            _PR60.ObservationProvenance("obs", "normalizer", "v1", "provider", _PR60.EvidenceAuthority.PROVIDER),
        ),
    )
    case = _PR61.development_cases()[0]
    packet = _PR62.make_blinded_packet(case)
    candidate = _PR62.AnnotationRecord(
        "candidate-a", packet.case_alias, packet.content_digest, packet.rubric_version,
        packet.packet_version, "aligned", "resolved", "sufficient", 0.5,
    )
    candidate.validate(packet)
    altered_packet = replace(packet, proposed_successor="tampered")
    packet_mutation_rejected = False
    try:
        candidate.validate(altered_packet)
    except ValueError:
        packet_mutation_rejected = True
    disagreement = _PR62.compare_reviewers((candidate, replace(candidate, reviewer_alias="reviewer-b", semantic_alignment="misaligned")))[0]
    controls = (
        _control("exact_trusted_observation", exact.semantic_alignment is _PR60.SemanticStatus.CORRECT, "exact attestation is accepted"),
        _control("correct_id_wrong_meaning", wrong_meaning_same_id.semantic_alignment is _PR60.SemanticStatus.UNVERIFIED, "same ID cannot hide a changed semantic target"),
        _control("changed_id_same_meaning", changed_id_same_meaning.semantic_alignment is _PR60.SemanticStatus.UNVERIFIED, "changed snapshot cannot reuse attestation"),
        _control("omission_is_not_resolution", omitted.ambiguity_resolution is _PR60.SemanticStatus.UNVERIFIED, "omitted ambiguity remains unverified"),
        _control("invalid_mode_fails_closed", invalid_mode.semantic_alignment is _PR60.SemanticStatus.UNVERIFIED, "plain string mode is rejected"),
        _control("provider_evidence_is_not_independent", provider_only.ambiguity_resolution is _PR60.SemanticStatus.UNVERIFIED, "provider evidence is rejected"),
        _control("same_packet_alias_changed_content", packet_mutation_rejected, "content-bound packet rejects mutation"),
        _control("candidate_labels_are_not_gold", candidate.annotation_kind is _PR62.AnnotationKind.CANDIDATE, "fixture annotations remain candidate-scoped"),
        _control("no_automatic_adjudication", disagreement["unresolved_disagreement"] and not disagreement["adjudicated"], "disagreement is retained as unresolved"),
        _control("private_holdout_required", _PR61.holdout_manifest()["private_holdout_ready"] is False, "disclosed fixtures cannot satisfy private holdout gate"),
    )
    return controls


def _default_packets() -> dict[str, Any]:
    return {case.case_id: _PR62.make_blinded_packet(case) for case in _PR61.development_cases()}


def evaluate_annotations(
    annotations: Iterable[Any] = (),
    *,
    packets: Iterable[Any] = (),
    registry: Any | None = None,
    verification_records: Iterable[Any] = (),
) -> dict[str, Any]:
    """Accept only registry-verified independent records and compute metrics."""

    packet_map = {packet.case_alias: packet for packet in packets}
    if not packet_map:
        packet_map = {packet.case_alias: packet for packet in _default_packets().values()}
    record_map: dict[tuple[str, str], list[Any]] = {}
    for record in verification_records:
        record_map.setdefault((record.packet_id, record.annotation_digest), []).append(record)
    accepted: list[Any] = []
    rejected = 0
    seen_submission_keys: set[tuple[str, str]] = set()
    for annotation in annotations:
        packet = packet_map.get(annotation.case_alias)
        if packet is None or registry is None:
            rejected += 1
            continue
        submission_key = (packet.packet_id, annotation.reviewer_alias)
        if submission_key in seen_submission_keys:
            # A reviewer may not inflate metrics by submitting the same packet
            # more than once.  Keep the first exact, host-verified submission.
            rejected += 1
            continue
        digest = _PR62.annotation_digest(annotation)
        records = record_map.get((packet.packet_id, digest), ())
        if len(records) != 1:
            rejected += 1
            continue
        record = records[0]
        try:
            _PR62.attest_host_annotation(record, packet=packet, annotation=annotation, registry=registry)
        except ValueError:
            rejected += 1
        else:
            seen_submission_keys.add(submission_key)
            accepted.append(annotation)
    return {"accepted": tuple(accepted), "rejected": rejected, "attestation_accepted": len(accepted), "attestation_rejected": rejected}


def _metric(accepted: list[Any], field: str, value: str, development_count: int) -> dict[str, int]:
    reviewable = {record.case_alias for record in accepted if not record.abstained and getattr(record, field) == value and record.evidence_sufficiency == "sufficient"}
    denominator = len({record.case_alias for record in accepted if not record.abstained and record.evidence_sufficiency == "sufficient"})
    return {"numerator": len(reviewable), "denominator": denominator, "missing": max(0, development_count - denominator)}


def _verified_reviewer_count(accepted: Iterable[Any], registry: Any | None) -> int:
    """Count identities represented by accepted host-verified annotations.

    Registry membership alone is only a configured capability, not evidence that
    a reviewer actually supplied an admissible annotation.  Aliases are mapped
    back to stable identity keys and duplicate identity keys fail closed.
    """

    if registry is None:
        return 0
    identities = {
        reviewer.reviewer_alias: reviewer.identity_key
        for reviewer in registry.reviewers
        if reviewer.independent and reviewer.approved
    }
    keys = {identities[record.reviewer_alias] for record in accepted if record.reviewer_alias in identities}
    return len(keys) if len(keys) == len({record.reviewer_alias for record in accepted if record.reviewer_alias in identities}) else 0


def run_offline_evaluation(
    annotations: Iterable[Any] = (),
    *,
    registry: Any | None = None,
    verification_records: Iterable[Any] = (),
    private_holdout_ready: bool | None = None,
) -> dict[str, Any]:
    annotation_list = list(annotations)
    cases = _PR61.corpus()
    for case in cases:
        _PR61.validate_case(case)
    development = _PR61.development_cases()
    controls = run_negative_controls()
    accepted_data = evaluate_annotations(annotation_list, registry=registry, verification_records=verification_records)
    accepted = list(accepted_data["accepted"])
    alignment = _metric(accepted, "semantic_alignment", "aligned", len(development))
    resolution = _metric(accepted, "ambiguity_resolution", "resolved", len(development))
    reviewers = _verified_reviewer_count(accepted, registry)
    disagreement = _PR62.compare_reviewers(accepted)
    private_ready = _PR61.holdout_manifest()["private_holdout_ready"] if private_holdout_ready is None else private_holdout_ready
    negative_passed = all(control["passed"] for control in controls)
    no_unresolved_disagreement = not any(item["unresolved_disagreement"] for item in disagreement)
    attestation_integrity = accepted_data["rejected"] == 0
    ready = bool(
        private_ready
        and reviewers >= 2
        and negative_passed
        and no_unresolved_disagreement
        and attestation_integrity
        and accepted
    )
    return {
        "record_type": "pr63_offline_evaluation",
        "protocol_version": PROTOCOL_VERSION,
        "corpus_version": _PR61.CORPUS_VERSION,
        "case_count": len(cases),
        "development_count": len(development),
        "disclosed_fixture_count": len(cases) - len(development),
        "primary_metric": {"name": "semantic_target_alignment", **alignment, "status": "evaluated" if alignment["denominator"] else "not_evaluated"},
        "secondary_metrics": {
            "ambiguity_resolution": resolution,
            "literal_target_retention": {"numerator": 0, "denominator": 0, "missing": len(development)},
            "structural_binding_conformance": {"numerator": 0, "denominator": 0, "missing": len(development)},
            "unsupported_assertion_rate": {"numerator": 0, "denominator": 0, "missing": len(development)},
        },
        "annotation_counts": {
            "submitted": len(annotation_list),
            "accepted": len(accepted),
            "rejected": accepted_data["rejected"],
            "abstained": sum(record.abstained for record in accepted),
            "indeterminate": sum(record.semantic_alignment == "indeterminate" for record in accepted),
        },
        "reviewer_disagreement": list(disagreement),
        "attestation": {"accepted": accepted_data["attestation_accepted"], "rejected": accepted_data["attestation_rejected"]},
        "negative_controls": list(controls),
        "negative_controls_passed": negative_passed,
        "readiness": {
            "status": "ready_for_live_evaluation" if ready else READINESS_STATUS,
            "frozen_rubric": True,
            "corpus_integrity": True,
            "condition_leakage_tested": True,
            "independent_gold_available": False,
            "independent_reviewer_count": reviewers,
            "verified_reviewer_count": reviewers,
            "private_holdout_ready": bool(private_ready),
            "attestation_integrity": attestation_integrity,
            "no_unresolved_disagreement": no_unresolved_disagreement,
            "real_model_calls": False,
            "ready_for_live_evaluation": ready,
        },
        "real_model_calls": False,
        "production_authority_changed": False,
    }


if __name__ == "__main__":
    print(json.dumps(run_offline_evaluation(), ensure_ascii=False, indent=2, sort_keys=True))
