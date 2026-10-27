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
        "indeterminate": 0,
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
    assert readiness["reviewer_registry_attested"] is False
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


def _verified_case_fixture(annotations, packet):
    identities = tuple(
        _MODULE._PR62.ReviewerIdentity(annotation.reviewer_alias, f"identity-{annotation.reviewer_alias}", True)
        for annotation in annotations
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
    records = tuple(
        _MODULE._PR62.HostVerificationRecord(
            packet.packet_id, packet.content_digest, _MODULE._PR62.annotation_digest(annotation),
            packet.rubric_version, annotation.reviewer_alias, "source", "normalizer", "v1",
            _MODULE._PR62.VerificationStage.EVIDENCE_VERIFIED, "independent source",
        )
        for annotation in annotations
    )
    return _MODULE._PR62.HostRegistry("registry-case", identities, assignments, evidence), records


def test_abstentions_do_not_change_case_outcome_or_metrics_end_to_end():
    packet, pair, _registry, _records = _verified_pair()
    first, second = pair

    def evaluate(completed, abstained):
        annotations = tuple(completed) + (abstained,)
        registry, records = _verified_case_fixture(annotations, packet)
        report = _MODULE.run_offline_evaluation(
            annotations, registry=registry, verification_records=records,
        )
        return report, next(item for item in report["review_coverage"] if item["case_alias"] == packet.case_alias)

    abstained_misaligned = replace(
        second, reviewer_alias="reviewer-c", abstained=True,
        abstention_reason="no basis", semantic_alignment="misaligned",
    )
    aligned_report, aligned_item = evaluate((first, second), abstained_misaligned)
    assert aligned_item["semantic_outcome"] == "aligned"
    assert aligned_report["primary_metric"]["numerator"] == 1

    completed_misaligned = replace(first, semantic_alignment="misaligned")
    completed_misaligned_b = replace(second, semantic_alignment="misaligned")
    abstained_aligned = replace(
        second, reviewer_alias="reviewer-c", abstained=True,
        abstention_reason="no basis", semantic_alignment="aligned",
    )
    misaligned_report, misaligned_item = evaluate(
        (completed_misaligned, completed_misaligned_b), abstained_aligned
    )
    assert misaligned_item["semantic_outcome"] == "misaligned"
    assert misaligned_report["primary_metric"]["numerator"] == 0

    unresolved = replace(first, ambiguity_resolution="not_resolved")
    unresolved_b = replace(second, ambiguity_resolution="not_resolved")
    abstained_resolved = replace(
        second, reviewer_alias="reviewer-c", abstained=True,
        abstention_reason="no basis", ambiguity_resolution="resolved",
    )
    unresolved_report, unresolved_item = evaluate((unresolved, unresolved_b), abstained_resolved)
    assert unresolved_item["semantic_outcome"] == "aligned"
    assert unresolved_report["secondary_metrics"]["ambiguity_resolution"]["numerator"] == 0

    indeterminate = replace(
        first, semantic_alignment="indeterminate", ambiguity_resolution="indeterminate",
        evidence_sufficiency="not_available",
    )
    indeterminate_b = replace(
        second, semantic_alignment="indeterminate", ambiguity_resolution="indeterminate",
        evidence_sufficiency="not_available",
    )
    indeterminate_report, indeterminate_item = evaluate((indeterminate, indeterminate_b), abstained_aligned)
    assert indeterminate_item["semantic_outcome"] == "indeterminate"
    assert indeterminate_report["primary_metric"]["numerator"] == 0
    assert indeterminate_report["primary_metric"]["indeterminate"] == 1


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
    assert report["readiness"]["synthetic_mechanics_passed"] is True
    assert report["readiness"]["synthetic_full_gate_passed"] is False
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
    assert report["readiness"]["reviewer_registry_attested"] is False
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


def test_one_reviewer_on_two_cases_remains_one_verified_identity():
    _packet, annotations, registry, _records = _verified_pair()
    second_packet = _MODULE._PR62.make_blinded_packet(_MODULE._PR61.development_cases()[1])
    second = replace(
        annotations[0],
        case_alias=second_packet.case_alias,
        packet_content_digest=second_packet.content_digest,
        rubric_version=second_packet.rubric_version,
        packet_version=second_packet.packet_version,
    )
    assert _MODULE._verified_reviewer_count((annotations[0], second), registry) == 1


def test_authenticated_holdout_manifest_is_explicit_but_does_not_skip_coverage():
    _packet, annotations, registry, records = _verified_pair()
    registry = replace(
        registry,
        registry_attestation=_MODULE._PR62.RegistryAttestation(
            registry.registry_id,
            "external-host",
            "a" * 64,
            True,
            registry_version=_MODULE._PR62.REGISTRY_VERSION,
            registry_digest=registry.snapshot_digest(),
        ),
    )
    manifest = _MODULE.PrivateHoldoutManifest(
        "private-1",
        _MODULE._PR61.CORPUS_VERSION,
        _MODULE._PR62.RUBRIC_VERSION,
        12,
        "a" * 64,
    )
    attestation = _MODULE.HostHoldoutAttestation(
        manifest,
        registry.registry_id,
        "b" * 64,
        True,
        manifest.content_digest(),
    )
    class TrustedSource(_MODULE._PR62.HostTrustSource):
        host_owned_capability = True
        issuer_id = "test-issuer"
        _capability_token = _MODULE._PR62._HOST_TRUST_CAPABILITY

        def verify_registry(self, _attestation, _registry, _digest):
            return True

        def verify_holdout(self, _attestation, _manifest, candidate, _digest):
            return candidate.registry_id == registry.registry_id

    report = _MODULE.run_offline_evaluation(
        annotations,
        registry=registry,
        verification_records=records,
        holdout_attestation=attestation,
        trusted_source=TrustedSource(),
    )
    assert report["readiness"]["holdout_attestation_verified"] is True
    assert report["readiness"]["reviewer_registry_attested"] is True
    assert report["readiness"]["coverage_complete"] is False
    assert report["readiness"]["ready_for_live_evaluation"] is False
    assert _MODULE._holdout_is_trusted(
        replace(attestation, host_registry_id="other-registry"),
        registry=registry,
        trusted_source=TrustedSource(),
        corpus_version=_MODULE._PR61.CORPUS_VERSION,
        rubric_version=_MODULE._PR62.RUBRIC_VERSION,
    ) is False
    assert _MODULE._holdout_is_trusted(
        replace(attestation, manifest_digest="c" * 64),
        registry=registry,
        trusted_source=TrustedSource(),
        corpus_version=_MODULE._PR61.CORPUS_VERSION,
        rubric_version=_MODULE._PR62.RUBRIC_VERSION,
    ) is False
    assert _MODULE._holdout_is_trusted(
        replace(attestation, manifest=replace(manifest, case_count=13)),
        registry=registry,
        trusted_source=TrustedSource(),
        corpus_version=_MODULE._PR61.CORPUS_VERSION,
        rubric_version=_MODULE._PR62.RUBRIC_VERSION,
    ) is False


def test_invalid_readiness_mode_fails_closed():
    for mode in ("caller-claimed", ["real"]):
        report = _MODULE.run_offline_evaluation(readiness_mode=mode)
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


def test_holdout_verified_flag_is_required_even_for_trusted_source():
    _packet, annotations, registry, records = _verified_pair()
    registry = replace(
        registry,
        registry_attestation=_MODULE._PR62.RegistryAttestation(
            registry.registry_id, "external-host", "a" * 64, True,
            registry_version=_MODULE._PR62.REGISTRY_VERSION,
            registry_digest=registry.snapshot_digest(),
        ),
    )
    manifest = _MODULE.PrivateHoldoutManifest(
        "private-1", _MODULE._PR61.CORPUS_VERSION, _MODULE._PR62.RUBRIC_VERSION, 12, "a" * 64
    )
    attestation = _MODULE.HostHoldoutAttestation(
        manifest, registry.registry_id, "b" * 64, False, manifest.content_digest()
    )

    class TrustedSource(_MODULE._PR62.HostTrustSource):
        host_owned_capability = True
        issuer_id = "test-issuer"
        _capability_token = _MODULE._PR62._HOST_TRUST_CAPABILITY

        def verify_registry(self, _attestation, _registry, _digest):
            return True

        def verify_holdout(self, *_args):
            return True

    assert _MODULE._holdout_is_trusted(
        attestation,
        registry=registry,
        trusted_source=TrustedSource(),
        corpus_version=_MODULE._PR61.CORPUS_VERSION,
        rubric_version=_MODULE._PR62.RUBRIC_VERSION,
    ) is False


def test_indeterminate_consensus_is_covered_but_not_missing():
    packet, annotations, registry, records = _verified_pair()
    indeterminate = tuple(
        replace(annotation, semantic_alignment="indeterminate", ambiguity_resolution="indeterminate", evidence_sufficiency="not_available")
        for annotation in annotations
    )
    indeterminate_records = tuple(
        replace(record, annotation_digest=_MODULE._PR62.annotation_digest(annotation))
        for record, annotation in zip(records, indeterminate)
    )
    registry = replace(
        registry,
        evidence=tuple(
            replace(evidence, annotation_digest=_MODULE._PR62.annotation_digest(indeterminate[index]))
            for index, evidence in enumerate(registry.evidence)
        ),
    )
    report = _MODULE.run_offline_evaluation(
        indeterminate, registry=registry, verification_records=indeterminate_records
    )
    item = next(item for item in report["review_coverage"] if item["case_alias"] == packet.case_alias)
    assert item["review_coverage_complete"] is True
    assert item["reviewer_consensus"] is True
    assert item["semantic_evidence_sufficiency"] == "not_available"
    assert item["semantic_outcome"] == "indeterminate"
    assert report["coverage_policy"]["review_coverage_complete_case_count"] == 1
    assert report["coverage_policy"]["consensus_supported_case_count"] == 1
    assert report["primary_metric"]["missing"] == 11


def test_full_synthetic_mechanics_fixture_covers_all_development_cases():
    annotations = []
    identities = []
    assignments = []
    evidence = []
    records = []
    packets = tuple(_MODULE._default_packets().values())
    labels = (
        ("aligned", "resolved", "sufficient"),
        ("misaligned", "not_resolved", "sufficient"),
        ("indeterminate", "indeterminate", "not_available"),
        ("aligned", "resolved", "insufficient"),
    )
    for index, packet in enumerate(packets):
        if index >= 12:
            break
        for reviewer_number in range(2):
            alias = f"synthetic-{index}-{reviewer_number}"
            alignment, resolution, sufficiency = labels[index % len(labels)]
            annotation = _MODULE._PR62.AnnotationRecord(
                alias, packet.case_alias, packet.content_digest, packet.rubric_version,
                packet.packet_version, alignment, resolution, sufficiency, 0.5,
                annotation_kind=_MODULE._PR62.AnnotationKind.INDEPENDENT,
            )
            digest = _MODULE._PR62.annotation_digest(annotation)
            annotations.append(annotation)
            identities.append(_MODULE._PR62.ReviewerIdentity(alias, f"identity-{alias}", True))
            assignments.append(_MODULE._PR62.PacketAssignment(packet.packet_id, packet.content_digest, alias))
            evidence.append(_MODULE._PR62.VerifiedEvidenceRecord(
                packet.packet_id, packet.content_digest, alias, digest,
                packet.rubric_version, "source", "normalizer", "v1", True,
            ))
            records.append(_MODULE._PR62.HostVerificationRecord(
                packet.packet_id, packet.content_digest, digest, packet.rubric_version,
                alias, "source", "normalizer", "v1",
                _MODULE._PR62.VerificationStage.EVIDENCE_VERIFIED, "synthetic mechanics",
            ))
    registry = _MODULE._PR62.HostRegistry("synthetic-registry", tuple(identities), tuple(assignments), tuple(evidence))
    report = _MODULE.run_offline_evaluation(
        tuple(annotations), registry=registry, verification_records=tuple(records),
        private_holdout_ready=True, readiness_mode="synthetic", synthetic_gate_test=True,
    )
    assert report["annotation_counts"]["accepted"] == 24
    assert report["coverage_policy"]["coverage_complete"] is True
    assert report["coverage_policy"]["consensus_supported_case_count"] == 12
    assert report["readiness"]["synthetic_mechanics_passed"] is True
    assert report["readiness"]["synthetic_full_gate_passed"] is True
    assert report["readiness"]["ready_for_live_evaluation"] is False
    assert report["readiness"]["real_model_calls"] is False
    assert report["production_authority_changed"] is False
    assert report["coverage_policy"]["semantic_outcome_counts"]["indeterminate"] == 6


def test_arbitrary_always_true_source_cannot_open_real_readiness():
    annotations = []
    identities = []
    assignments = []
    evidence = []
    records = []
    for index, packet in enumerate(tuple(_MODULE._default_packets().values())[:12]):
        for reviewer_number in range(2):
            alias = f"adversarial-{index}-{reviewer_number}"
            annotation = _MODULE._PR62.AnnotationRecord(
                alias, packet.case_alias, packet.content_digest, packet.rubric_version,
                packet.packet_version, "aligned", "resolved", "sufficient", 0.5,
                annotation_kind=_MODULE._PR62.AnnotationKind.INDEPENDENT,
            )
            digest = _MODULE._PR62.annotation_digest(annotation)
            annotations.append(annotation)
            identities.append(_MODULE._PR62.ReviewerIdentity(alias, f"identity-{alias}", True))
            assignments.append(_MODULE._PR62.PacketAssignment(packet.packet_id, packet.content_digest, alias))
            evidence.append(_MODULE._PR62.VerifiedEvidenceRecord(
                packet.packet_id, packet.content_digest, alias, digest,
                packet.rubric_version, "source", "normalizer", "v1", True,
            ))
            records.append(_MODULE._PR62.HostVerificationRecord(
                packet.packet_id, packet.content_digest, digest, packet.rubric_version,
                alias, "source", "normalizer", "v1",
                _MODULE._PR62.VerificationStage.EVIDENCE_VERIFIED, "synthetic adversarial fixture",
            ))
    registry = _MODULE._PR62.HostRegistry(
        "adversarial-registry", tuple(identities), tuple(assignments), tuple(evidence)
    )
    registry = replace(
        registry,
        registry_attestation=_MODULE._PR62.RegistryAttestation(
            registry.registry_id, "caller-issuer", "a" * 64, True,
            registry_version=_MODULE._PR62.REGISTRY_VERSION,
            registry_digest=registry.snapshot_digest(),
        ),
    )
    manifest = _MODULE.PrivateHoldoutManifest(
        "adversarial-holdout", _MODULE._PR61.CORPUS_VERSION,
        _MODULE._PR62.RUBRIC_VERSION, 12, "b" * 64,
    )
    attestation = _MODULE.HostHoldoutAttestation(
        manifest, registry.registry_id, "c" * 64, True, manifest.content_digest()
    )

    class AlwaysTrueSource:
        def verify_registry(self, *_args):
            return True

        def verify_holdout(self, *_args):
            return True

    report = _MODULE.run_offline_evaluation(
        tuple(annotations), registry=registry, verification_records=tuple(records),
        holdout_attestation=attestation, trusted_source=AlwaysTrueSource(),
        readiness_mode="real",
    )
    assert report["readiness"]["holdout_attestation_verified"] is False
    assert report["readiness"]["reviewer_registry_attested"] is False
    assert report["readiness"]["ready_for_live_evaluation"] is False
    assert report["real_model_calls"] is False
    assert report["production_authority_changed"] is False


def test_abstention_policy_counts_only_completed_reviews_for_coverage_and_consensus():
    packet, pair, registry, _records = _verified_pair()
    first, second = pair
    abstained = replace(
        second, reviewer_alias="reviewer-c", abstained=True,
        abstention_reason="no sufficient basis",
    )
    registry = replace(
        registry,
        reviewers=registry.reviewers + (_MODULE._PR62.ReviewerIdentity("reviewer-c", "person-c", True),),
    )
    def coverage(records):
        return _MODULE._coverage(
            list(records), list(records), registry=registry,
            development_packets=(packet,),
        )[0]

    complete = coverage((first, second, abstained))
    assert complete["review_coverage_complete"] is True
    assert complete["reviewer_consensus"] is True
    assert complete["completed_annotations"] == 2
    assert complete["abstentions"] == 1
    assert complete["disagreement"] is False

    incomplete = coverage((first, abstained))
    assert incomplete["review_coverage_complete"] is False
    assert incomplete["semantic_outcome"] == "missing"

    disagreeing = coverage((first, replace(second, semantic_alignment="misaligned"), abstained))
    assert disagreeing["review_coverage_complete"] is True
    assert disagreeing["reviewer_consensus"] is False
    assert disagreeing["disagreement"] is True

    all_abstained = coverage((replace(first, abstained=True, abstention_reason="no basis"), abstained))
    assert all_abstained["review_coverage_complete"] is False
    assert all_abstained["semantic_outcome"] == "missing"
    assert all_abstained["disagreement"] is False

    indeterminate = coverage((
        replace(first, semantic_alignment="indeterminate", ambiguity_resolution="indeterminate", evidence_sufficiency="not_available"),
        replace(second, semantic_alignment="indeterminate", ambiguity_resolution="indeterminate", evidence_sufficiency="not_available"),
        abstained,
    ))
    assert indeterminate["review_coverage_complete"] is True
    assert indeterminate["reviewer_consensus"] is True
    assert indeterminate["semantic_outcome"] == "indeterminate"
