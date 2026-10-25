"""Deterministic offline calibration for the independent semantic protocol.

The runner composes frozen packet/annotation inputs with the existing PR60
host-evidence verifier. It reports calibration mechanics and readiness only;
fixture labels are never promoted to independent semantic truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


PROTOCOL_VERSION = "pr63-offline-evaluation-v1"
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
        expected.target_key,
        provenance.observation_id,
        provenance.normalizer_id,
        provenance.normalizer_version,
        provenance.source_id,
        tuple(evidence.source_id for evidence in observed.evidence),
        tuple(evidence.statement_key for evidence in observed.evidence),
        _PR60._observation_digest(expected, observed),
    )
    return _PR60.TrustedHostEvidenceResolver(frozenset((attestation,)))


def _verified_observation(target_key: str = "x", target_id: str = "id-x", *, resolution=None):
    resolution = resolution or _PR60.ResolutionStatus.RESOLVED
    provenance = _PR60.ObservationProvenance(
        "obs", "normalizer", "v1", "source", _PR60.EvidenceAuthority.HOST_INDEPENDENT
    )
    evidence = (
        _PR60.EvidenceReference(
            "source", _PR60.EvidenceAuthority.HOST_INDEPENDENT,
            _PR60.EvidenceStatus.VERIFIED, "evidence",
        ),
    )
    return _PR60.ObservedSemanticSnapshot(target_key, target_id, resolution, evidence, provenance)


def _control(name: str, condition: bool, detail: str) -> dict[str, Any]:
    return {"control": name, "passed": condition, "detail": detail}


def run_negative_controls() -> tuple[dict[str, Any], ...]:
    """Run deterministic controls for common evaluator and provenance failures."""

    expected = _PR60.SemanticExpectation("x", "id-x", ("evidence",))
    observed = _verified_observation()
    resolver = _trusted_resolver(expected, observed)
    exact = _PR60.verify_independent(expected, observed, resolver=resolver)
    changed_id = _PR60.verify_independent(
        expected, _verified_observation(target_id="other"), resolver=resolver
    )
    omitted = _PR60.verify_independent(
        expected, _verified_observation(resolution=_PR60.ResolutionStatus.OMITTED), resolver=resolver
    )
    invalid_mode = _PR60.verify_independent(
        expected, observed, mode="real_observation", resolver=resolver
    )
    provider_only = _PR60.verify_independent(
        expected,
        _PR60.ObservedSemanticSnapshot(
            "x", "id-x", _PR60.ResolutionStatus.RESOLVED,
            (_PR60.EvidenceReference("provider", _PR60.EvidenceAuthority.PROVIDER, _PR60.EvidenceStatus.VERIFIED, "evidence"),),
            _PR60.ObservationProvenance("obs", "normalizer", "v1", "provider", _PR60.EvidenceAuthority.PROVIDER),
        ),
    )
    packet = _PR62.make_blinded_packet(_PR61.corpus()[0])
    candidate = _PR62.AnnotationRecord(
        "candidate-a", packet.case_alias, packet.rubric_version, packet.packet_version,
        "aligned", "resolved", "sufficient", 0.5,
    )
    candidate.validate(packet)
    disagreement = _PR62.compare_reviewers((
        candidate,
        _PR62.AnnotationRecord(
            "reviewer-b", packet.case_alias, packet.rubric_version, packet.packet_version,
            "misaligned", "resolved", "sufficient", 0.5,
        ),
    ))[0]
    controls = (
        _control("exact_trusted_observation", exact.semantic_alignment is _PR60.SemanticStatus.CORRECT, "exact attestation is accepted"),
        _control("correct_id_wrong_meaning", changed_id.semantic_alignment is _PR60.SemanticStatus.UNVERIFIED, "changed snapshot cannot reuse attestation"),
        _control("omission_is_not_resolution", omitted.ambiguity_resolution is _PR60.SemanticStatus.UNVERIFIED, "omitted ambiguity remains unverified"),
        _control("invalid_mode_fails_closed", invalid_mode.semantic_alignment is _PR60.SemanticStatus.UNVERIFIED, "plain string mode is rejected"),
        _control("provider_evidence_is_not_independent", provider_only.ambiguity_resolution is _PR60.SemanticStatus.UNVERIFIED, "provider evidence is rejected"),
        _control("candidate_labels_are_not_gold", candidate.annotation_kind is _PR62.AnnotationKind.CANDIDATE, "fixture annotations remain candidate-scoped"),
        _control("no_automatic_adjudication", disagreement["unresolved_disagreement"] and not disagreement["adjudicated"], "disagreement is retained as unresolved"),
    )
    return controls


def run_offline_evaluation() -> dict[str, Any]:
    cases = _PR61.corpus()
    for case in cases:
        _PR61.validate_case(case)
    development = [case for case in cases if not case.holdout]
    controls = run_negative_controls()
    return {
        "record_type": "pr63_offline_evaluation",
        "protocol_version": PROTOCOL_VERSION,
        "corpus_version": _PR61.CORPUS_VERSION,
        "case_count": len(cases),
        "development_count": len(development),
        "holdout_count": len(cases) - len(development),
        "primary_metric": {
            "name": "semantic_target_alignment",
            "numerator": 0,
            "denominator": 0,
            "missing": len(development),
            "status": "not_evaluated",
        },
        "secondary_metrics": {
            "ambiguity_resolution": {"numerator": 0, "denominator": 0, "missing": len(development)},
            "literal_target_retention": {"numerator": 0, "denominator": 0, "missing": len(development)},
            "structural_binding_conformance": {"numerator": 0, "denominator": 0, "missing": len(development)},
            "unsupported_assertion_rate": {"numerator": 0, "denominator": 0, "missing": len(development)},
        },
        "negative_controls": list(controls),
        "negative_controls_passed": all(control["passed"] for control in controls),
        "readiness": {
            "status": READINESS_STATUS,
            "frozen_rubric": True,
            "corpus_integrity": True,
            "condition_leakage_tested": True,
            "independent_gold_available": False,
            "independent_reviewer_count": 0,
            "attestation_integrity": True,
            "real_model_calls": False,
            "ready_for_live_evaluation": False,
        },
        "real_model_calls": False,
        "production_authority_changed": False,
    }


if __name__ == "__main__":
    print(json.dumps(run_offline_evaluation(), ensure_ascii=False, indent=2, sort_keys=True))
