import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace


_PATH = Path(__file__).parents[1] / "research" / "pr62_blinded_annotation.py"
_SPEC = importlib.util.spec_from_file_location("pr62_blinded_annotation", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _case(family="genome_identity"):
    return SimpleNamespace(
        case_id="genome-dev-01",
        family=family,
        intended_target_key="genome_numerical_identity" if family == "genome_identity" else "intrinsic_present",
        initial_interpretation="Initial interpretation",
        clarification_question="What is the target?",
        proposed_successor="A bounded successor",
    )


def _annotation(packet, **changes):
    values = {
        "reviewer_alias": "reviewer-a",
        "case_alias": packet.case_alias,
        "packet_content_digest": packet.content_digest,
        "rubric_version": packet.rubric_version,
        "packet_version": packet.packet_version,
        "semantic_alignment": "aligned",
        "ambiguity_resolution": "resolved",
        "evidence_sufficiency": "sufficient",
        "confidence": 0.8,
    }
    values.update(changes)
    return _MODULE.AnnotationRecord(**values)


def _registry(packet, annotation, *, reviewer_alias="reviewer-a", independent=True, duplicate_identity=False):
    digest = _MODULE.annotation_digest(annotation)
    identities = (
        _MODULE.ReviewerIdentity(reviewer_alias, "person-a", independent),
        _MODULE.ReviewerIdentity("reviewer-copy", "person-a", independent),
    ) if duplicate_identity else (_MODULE.ReviewerIdentity(reviewer_alias, "person-a", independent),)
    return _MODULE.HostRegistry(
        "host-registry-1",
        identities,
        (_MODULE.PacketAssignment(packet.packet_id, packet.content_digest, reviewer_alias),),
        (_MODULE.VerifiedEvidenceRecord(
            packet.packet_id, packet.content_digest, reviewer_alias, digest,
            packet.rubric_version, "host-source", "host-normalizer", "v1", True,
        ),),
    )


def _verification(packet, annotation, *, stage=None, reviewer_alias="reviewer-a", provider=False):
    return _MODULE.HostVerificationRecord(
        packet.packet_id, packet.content_digest, _MODULE.annotation_digest(annotation),
        packet.rubric_version, reviewer_alias, "host-source", "host-normalizer", "v1",
        stage or _MODULE.VerificationStage.EVIDENCE_VERIFIED, "independent source", provider,
    )


def test_packet_is_blinded_and_uses_case_specific_semantic_description():
    genome = _MODULE.make_blinded_packet(
        _case(), condition="explicit_binding", model_name="Bonsai-secret", target_id="target-1"
    )
    time_packet = _MODULE.make_blinded_packet(_case("intrinsic_time"))
    public = genome.public_dict()
    assert "numerical identity" in public["intended_target_description"]
    assert "observer-relative" in time_packet.intended_target_description
    assert "explicit_binding" not in str(public)
    assert "Bonsai-secret" not in str(public)
    assert "target-1" not in str(public)


def test_annotation_requires_exact_packet_content_digest():
    packet = _MODULE.make_blinded_packet(_case())
    record = _annotation(packet)
    record.validate(packet)
    altered = replace(packet, proposed_successor="Changed successor")
    try:
        record.validate(altered)
    except ValueError as error:
        assert "content" in str(error)
    else:
        raise AssertionError("annotation was reused for changed packet content")


def test_annotation_validation_requires_abstention_reason_and_versions():
    packet = _MODULE.make_blinded_packet(_case())
    record = _annotation(packet, abstained=True, abstention_reason="successor is ambiguous")
    record.validate(packet)
    for changes in ({"abstained": True}, {"packet_version": "old"}, {"confidence": 2.0}):
        try:
            replace(_annotation(packet), **changes).validate(packet)
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed annotation accepted: {changes}")


def test_provider_payload_and_caller_stage_cannot_create_attestation():
    packet = _MODULE.make_blinded_packet(_case())
    annotation = _annotation(packet, annotation_kind=_MODULE.AnnotationKind.INDEPENDENT)
    for record in (
        _verification(packet, annotation, provider=True),
        _verification(packet, annotation, stage=_MODULE.VerificationStage.OBSERVATION_MATCHED),
    ):
        try:
            _MODULE.attest_host_annotation(record, packet=packet, annotation=annotation, registry=_registry(packet, annotation))
        except ValueError:
            pass
        else:
            raise AssertionError("untrusted record created an attestation")


def test_valid_attestation_requires_exact_host_registry_relationships():
    packet = _MODULE.make_blinded_packet(_case())
    annotation = _annotation(packet, annotation_kind=_MODULE.AnnotationKind.INDEPENDENT)
    annotation.validate(packet)
    attestation = _MODULE.attest_host_annotation(
        _verification(packet, annotation), packet=packet, annotation=annotation,
        registry=_registry(packet, annotation),
    )
    assert attestation.packet_content_digest == packet.content_digest
    assert attestation.annotation_digest == _MODULE.annotation_digest(annotation)


def test_source_and_normalizer_mismatch_cannot_reuse_registry_evidence():
    packet = _MODULE.make_blinded_packet(_case())
    annotation = _annotation(packet, annotation_kind=_MODULE.AnnotationKind.INDEPENDENT)
    bad_record = replace(_verification(packet, annotation), source_id="other-source")
    try:
        _MODULE.attest_host_annotation(
            bad_record, packet=packet, annotation=annotation, registry=_registry(packet, annotation)
        )
    except ValueError as error:
        assert "registry" in str(error)
    else:
        raise AssertionError("source mismatch reused verified evidence")


def test_forged_reviewer_duplicate_identity_and_candidate_are_rejected():
    packet = _MODULE.make_blinded_packet(_case())
    annotation = _annotation(packet)
    for registry, record in (
        (_registry(packet, annotation, independent=False), _verification(packet, annotation)),
        (_registry(packet, annotation, duplicate_identity=True), _verification(packet, annotation)),
        (_registry(packet, annotation), _verification(packet, annotation, reviewer_alias="reviewer-other")),
    ):
        try:
            _MODULE.attest_host_annotation(record, packet=packet, annotation=annotation, registry=registry)
        except ValueError:
            pass
        else:
            raise AssertionError("forged reviewer relationship was accepted")
    candidate = _annotation(packet, annotation_kind=_MODULE.AnnotationKind.CANDIDATE)
    try:
        _MODULE.attest_host_annotation(_verification(packet, candidate), packet=packet, annotation=candidate, registry=_registry(packet, candidate))
    except ValueError:
        pass
    else:
        raise AssertionError("candidate annotation was attested as independent")


def test_registry_membership_alone_is_not_live_trust():
    packet = _MODULE.make_blinded_packet(_case())
    annotation = _annotation(packet, annotation_kind=_MODULE.AnnotationKind.INDEPENDENT)
    registry = _registry(packet, annotation)
    assert registry.trusted_for_live_evaluation() is False
    attested = replace(
        registry,
        registry_attestation=_MODULE.RegistryAttestation(
            registry.registry_id,
            "external-host",
            "a" * 64,
            True,
            registry_version=_MODULE.REGISTRY_VERSION,
            registry_digest=registry.snapshot_digest(),
        ),
    )
    class TrustedSource:
        def verify_registry(self, attestation, candidate, digest):
            return attestation.source_id == "external-host" and candidate is attested and digest == candidate.snapshot_digest()

    assert attested.trusted_for_live_evaluation(TrustedSource()) is True


def test_registry_snapshot_changes_invalidate_prior_attestation():
    packet = _MODULE.make_blinded_packet(_case())
    annotation = _annotation(packet, annotation_kind=_MODULE.AnnotationKind.INDEPENDENT)
    registry = _registry(packet, annotation)
    attested = replace(
        registry,
        registry_attestation=_MODULE.RegistryAttestation(
            registry.registry_id,
            "external-host",
            "a" * 64,
            True,
            registry_version=_MODULE.REGISTRY_VERSION,
            registry_digest=registry.snapshot_digest(),
        ),
    )
    changed = replace(attested, reviewers=(replace(attested.reviewers[0], approved=False),))

    class TrustedSource:
        def verify_registry(self, _attestation, _candidate, _digest):
            return True

    assert attested.trusted_for_live_evaluation(TrustedSource()) is True
    assert changed.trusted_for_live_evaluation(TrustedSource()) is False


def test_reviewer_disagreement_remains_visible_and_unadjudicated():
    packet = _MODULE.make_blinded_packet(_case())
    first = _annotation(packet, reviewer_alias="reviewer-a")
    second = _annotation(packet, reviewer_alias="reviewer-b", semantic_alignment="misaligned")
    summary = _MODULE.compare_reviewers((first, second))[0]
    assert summary["reviewer_count"] == 2
    assert summary["alignment_agreement"] is False
    assert summary["unresolved_disagreement"] is True
    assert summary["adjudicated"] is False


def test_public_disagreement_summary_redacts_private_reviewer_material():
    packet = _MODULE.make_blinded_packet(_case())
    first = _annotation(
        packet,
        annotation_kind=_MODULE.AnnotationKind.INDEPENDENT,
        abstained=True,
        abstention_reason="PRIVATE-ABSTENTION-MARKER",
        rationale_span_refs=("PRIVATE-RATIONALE-MARKER",),
    )
    second = _annotation(
        packet,
        reviewer_alias="reviewer-b",
        annotation_kind=_MODULE.AnnotationKind.INDEPENDENT,
    )
    public = _MODULE.compare_reviewers((first, second))
    serialized = json.dumps(public, sort_keys=True)
    assert "PRIVATE-ABSTENTION-MARKER" not in serialized
    assert "PRIVATE-RATIONALE-MARKER" not in serialized
    assert "raw_judgments" not in serialized
    assert "PRIVATE-ABSTENTION-MARKER" not in json.dumps(first.public_dict(), sort_keys=True)
    assert "PRIVATE-RATIONALE-MARKER" not in json.dumps(first.public_dict(), sort_keys=True)
    assert public[0]["abstention_reason_codes"] == ["abstained", "not_abstained"]
    private = _MODULE.compare_reviewers_private((first, second))
    assert "PRIVATE-ABSTENTION-MARKER" in json.dumps(private, sort_keys=True)


def test_annotation_manifest_keeps_provider_and_condition_data_private():
    path = Path(__file__).parents[3] / "docs" / "reports" / "pr62-annotation-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["raw_provider_payload_public"] is False
    assert manifest["condition_metadata_public"] is False
    assert manifest["automatic_adjudication"] is False
    assert manifest["provider_can_create_attestation"] is False
