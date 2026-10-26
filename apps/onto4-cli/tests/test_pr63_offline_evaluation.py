import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import sys


_PATH = Path(__file__).parents[1] / "research" / "pr63_offline_evaluation.py"
_SPEC = importlib.util.spec_from_file_location("pr63_offline_evaluation", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_negative_controls_all_pass_without_model_calls():
    controls = _MODULE.run_negative_controls()
    assert controls
    assert all(control["passed"] for control in controls)
    assert {control["control"] for control in controls} >= {
        "exact_trusted_observation",
        "correct_id_wrong_meaning",
        "omission_is_not_resolution",
        "invalid_mode_fails_closed",
        "provider_evidence_is_not_independent",
    }


def test_offline_evaluation_reports_missing_semantic_denominators():
    report = _MODULE.run_offline_evaluation()
    assert report["case_count"] == 16
    assert report["development_count"] == 12
    assert report["disclosed_fixture_count"] == 4
    assert report["primary_metric"] == {
        "name": "semantic_target_alignment",
        "numerator": 0,
        "denominator": 0,
        "missing": 12,
        "status": "not_evaluated",
    }
    assert report["negative_controls_passed"] is True
    assert report["real_model_calls"] is False
    assert report["annotation_counts"] == {
        "submitted": 0, "accepted": 0, "rejected": 0, "abstained": 0, "indeterminate": 0
    }


def test_readiness_gate_stops_before_live_evaluation_without_independent_reviewers():
    readiness = _MODULE.run_offline_evaluation()["readiness"]
    assert readiness["frozen_rubric"] is True
    assert readiness["attestation_integrity"] is True
    assert readiness["independent_gold_available"] is False
    assert readiness["independent_reviewer_count"] == 0
    assert readiness["verified_reviewer_count"] == 0
    assert readiness["no_unresolved_disagreement"] is True
    assert readiness["ready_for_live_evaluation"] is False
    assert readiness["status"] == "pending_independent_annotations"


def test_offline_artifact_is_json_safe_and_has_no_provider_payload():
    report = _MODULE.run_offline_evaluation()
    serialized = json.dumps(report, sort_keys=True)
    assert "provider_payload" not in serialized
    assert "Bonsai" not in serialized
    assert report["production_authority_changed"] is False


def test_committed_offline_artifact_matches_runner():
    path = Path(__file__).parents[3] / "docs" / "reports" / "pr63-offline-evaluation.json"
    assert json.loads(path.read_text(encoding="utf-8")) == _MODULE.run_offline_evaluation()


def test_readiness_metrics_are_computed_from_registry_verified_annotation():
    case = _MODULE._PR61.development_cases()[0]
    packet = _MODULE._PR62.make_blinded_packet(case)
    annotation = _MODULE._PR62.AnnotationRecord(
        "reviewer-a", packet.case_alias, packet.content_digest, packet.rubric_version,
        packet.packet_version, "aligned", "resolved", "sufficient", 0.9,
        annotation_kind=_MODULE._PR62.AnnotationKind.INDEPENDENT,
    )
    digest = _MODULE._PR62.annotation_digest(annotation)
    registry = _MODULE._PR62.HostRegistry(
        "registry-1",
        (_MODULE._PR62.ReviewerIdentity("reviewer-a", "person-a", True),),
        (_MODULE._PR62.PacketAssignment(packet.packet_id, packet.content_digest, "reviewer-a"),),
        (_MODULE._PR62.VerifiedEvidenceRecord(
            packet.packet_id, packet.content_digest, "reviewer-a", digest,
            packet.rubric_version, "source", "normalizer", "v1", True,
        ),),
    )
    record = _MODULE._PR62.HostVerificationRecord(
        packet.packet_id, packet.content_digest, digest, packet.rubric_version,
        "reviewer-a", "source", "normalizer", "v1",
        _MODULE._PR62.VerificationStage.EVIDENCE_VERIFIED, "independent source",
    )
    report = _MODULE.run_offline_evaluation(
        (annotation,), registry=registry, verification_records=(record,)
    )
    assert report["annotation_counts"]["accepted"] == 1
    assert report["attestation"] == {"accepted": 1, "rejected": 0}
    assert report["primary_metric"]["numerator"] == 0
    assert report["primary_metric"]["denominator"] == 0
    assert report["primary_metric"]["missing"] == 12
    assert report["readiness"]["independent_reviewer_count"] == 1
    assert report["readiness"]["verified_reviewer_count"] == 1
    assert report["readiness"]["ready_for_live_evaluation"] is False


def _verified_pair(*, disagree=False):
    case = _MODULE._PR61.development_cases()[0]
    packet = _MODULE._PR62.make_blinded_packet(case)
    first = _MODULE._PR62.AnnotationRecord(
        "reviewer-a", packet.case_alias, packet.content_digest, packet.rubric_version,
        packet.packet_version, "aligned", "resolved", "sufficient", 0.9,
        annotation_kind=_MODULE._PR62.AnnotationKind.INDEPENDENT,
    )
    second = replace(
        first,
        reviewer_alias="reviewer-b",
        semantic_alignment="misaligned" if disagree else "aligned",
    )
    annotations = (first, second)
    identities = (
        _MODULE._PR62.ReviewerIdentity("reviewer-a", "person-a", True),
        _MODULE._PR62.ReviewerIdentity("reviewer-b", "person-b", True),
    )
    assignments = tuple(
        _MODULE._PR62.PacketAssignment(packet.packet_id, packet.content_digest, annotation.reviewer_alias)
        for annotation in annotations
    )
    evidence = tuple(
        _MODULE._PR62.VerifiedEvidenceRecord(
            packet.packet_id, packet.content_digest, annotation.reviewer_alias,
            _MODULE._PR62.annotation_digest(annotation), packet.rubric_version,
            "source", "normalizer", "v1", True,
        )
        for annotation in annotations
    )
    registry = _MODULE._PR62.HostRegistry("registry-2", identities, assignments, evidence)
    records = tuple(
        _MODULE._PR62.HostVerificationRecord(
            packet.packet_id, packet.content_digest, _MODULE._PR62.annotation_digest(annotation),
            packet.rubric_version, annotation.reviewer_alias, "source", "normalizer", "v1",
            _MODULE._PR62.VerificationStage.EVIDENCE_VERIFIED, "independent source",
        )
        for annotation in annotations
    )
    return packet, annotations, registry, records


def test_readiness_requires_two_verified_reviewer_identities_and_accepts_positive_gate():
    _packet, annotations, registry, records = _verified_pair()
    report = _MODULE.run_offline_evaluation(
        annotations,
        registry=registry,
        verification_records=records,
        private_holdout_ready=True,
        readiness_mode="synthetic",
        synthetic_gate_test=True,
    )
    assert report["readiness"]["independent_reviewer_count"] == 2
    assert report["readiness"]["verified_reviewer_count"] == 2
    assert report["readiness"]["no_unresolved_disagreement"] is True
    assert report["readiness"]["synthetic_gate_passed"] is True
    assert report["readiness"]["coverage_complete"] is False
    assert report["readiness"]["ready_for_live_evaluation"] is False


def test_unresolved_disagreement_blocks_readiness_even_with_two_verified_reviewers():
    _packet, annotations, registry, records = _verified_pair(disagree=True)
    report = _MODULE.run_offline_evaluation(
        annotations,
        registry=registry,
        verification_records=records,
        private_holdout_ready=True,
        readiness_mode="synthetic",
        synthetic_gate_test=True,
    )
    assert report["readiness"]["verified_reviewer_count"] == 2
    assert report["readiness"]["no_unresolved_disagreement"] is False
    assert report["readiness"]["ready_for_live_evaluation"] is False


def test_duplicate_submission_by_one_reviewer_is_rejected_and_cannot_inflate_gate():
    packet, annotations, registry, records = _verified_pair()
    duplicate = replace(annotations[0], ambiguity_resolution="not_resolved")
    duplicate_record = replace(
        records[0], annotation_digest=_MODULE._PR62.annotation_digest(duplicate)
    )
    registry = replace(
        registry,
        evidence=registry.evidence + (
            _MODULE._PR62.VerifiedEvidenceRecord(
                packet.packet_id, packet.content_digest, "reviewer-a",
                _MODULE._PR62.annotation_digest(duplicate), packet.rubric_version,
                "source", "normalizer", "v1", True,
            ),
        ),
    )
    report = _MODULE.run_offline_evaluation(
        (annotations[0], duplicate, annotations[1]),
        registry=registry,
        verification_records=(records[0], duplicate_record, records[1]),
        private_holdout_ready=True,
        readiness_mode="synthetic",
        synthetic_gate_test=True,
    )
    assert report["annotation_counts"]["accepted"] == 2
    assert report["annotation_counts"]["rejected"] == 1
    assert report["readiness"]["verified_reviewer_count"] == 2
    assert report["readiness"]["attestation_integrity"] is False
    assert report["readiness"]["ready_for_live_evaluation"] is False


def test_caller_boolean_cannot_authorize_real_private_holdout():
    _packet, annotations, registry, records = _verified_pair()
    report = _MODULE.run_offline_evaluation(
        annotations,
        registry=registry,
        verification_records=records,
        private_holdout_ready=True,
    )
    assert report["readiness"]["private_holdout_ready"] is False
    assert report["readiness"]["holdout_attestation_verified"] is False
    assert report["readiness"]["ready_for_live_evaluation"] is False


def test_two_reviewers_on_one_case_do_not_complete_corpus_coverage():
    _packet, annotations, registry, records = _verified_pair()
    report = _MODULE.run_offline_evaluation(
        annotations,
        registry=registry,
        verification_records=records,
        readiness_mode="synthetic",
        synthetic_gate_test=True,
        private_holdout_ready=True,
    )
    assert report["coverage_policy"]["required_case_count"] == 12
    assert report["coverage_policy"]["consensus_supported_case_count"] == 1
    assert report["coverage_policy"]["coverage_complete"] is False
    assert report["primary_metric"]["denominator"] == 1
    assert report["primary_metric"]["missing"] == 11
    assert report["readiness"]["ready_for_live_evaluation"] is False


def test_invalid_readiness_mode_fails_closed():
    report = _MODULE.run_offline_evaluation(readiness_mode="caller-claimed")
    assert report["readiness"]["status"] == "invalid_readiness_mode"
    assert report["readiness"]["ready_for_live_evaluation"] is False


def test_public_report_never_contains_private_reviewer_text():
    packet, annotations, registry, records = _verified_pair()
    sensitive = replace(
        annotations[0],
        abstained=True,
        abstention_reason="PRIVATE-REPORT-MARKER",
        rationale_span_refs=("PRIVATE-SPAN-MARKER",),
    )
    sensitive_record = replace(records[0], annotation_digest=_MODULE._PR62.annotation_digest(sensitive))
    registry = replace(
        registry,
        evidence=tuple(
            evidence if evidence.reviewer_alias != "reviewer-a" else replace(
                evidence, annotation_digest=_MODULE._PR62.annotation_digest(sensitive)
            )
            for evidence in registry.evidence
        ),
    )
    report = _MODULE.run_offline_evaluation(
        (sensitive, annotations[1]),
        registry=registry,
        verification_records=(sensitive_record, records[1]),
    )
    serialized = json.dumps(report, sort_keys=True)
    assert "PRIVATE-REPORT-MARKER" not in serialized
    assert "PRIVATE-SPAN-MARKER" not in serialized
