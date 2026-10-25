import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


_PATH = Path(__file__).parents[1] / "research" / "pr62_blinded_annotation.py"
_SPEC = importlib.util.spec_from_file_location("pr62_blinded_annotation", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _case():
    return SimpleNamespace(
        case_id="genome-dev-01",
        initial_interpretation="Initial interpretation",
        clarification_question="What is the target?",
        proposed_successor="A bounded successor",
    )


def _annotation(packet, **changes):
    values = {
        "reviewer_alias": "reviewer-a",
        "case_alias": packet.case_alias,
        "rubric_version": packet.rubric_version,
        "packet_version": packet.packet_version,
        "semantic_alignment": "aligned",
        "ambiguity_resolution": "resolved",
        "evidence_sufficiency": "sufficient",
        "confidence": 0.8,
    }
    values.update(changes)
    return _MODULE.AnnotationRecord(**values)


def test_packet_is_blinded_and_discards_condition_model_and_target_id():
    packet = _MODULE.make_blinded_packet(
        _case(), condition="explicit_binding", model_name="Bonsai-secret", target_id="target-1"
    )
    public = packet.public_dict()
    assert public["case_alias"] == public["packet_id"]
    assert public["neutral_target_alias"] == "target-under-review"
    assert "explicit_binding" not in str(public)
    assert "Bonsai-secret" not in str(public)
    assert "target-1" not in str(public)


def test_annotation_validates_against_exact_packet_and_requires_abstention_reason():
    packet = _MODULE.make_blinded_packet(_case())
    record = _annotation(packet, abstained=True, abstention_reason="successor is ambiguous")
    record.validate(packet)
    try:
        _annotation(packet, abstained=True).validate(packet)
    except ValueError as error:
        assert "abstention" in str(error)
    else:
        raise AssertionError("abstention without reason was accepted")


def test_stale_packet_version_and_invalid_labels_fail_closed():
    packet = _MODULE.make_blinded_packet(_case())
    for changes in (
        {"case_alias": "packet-other"},
        {"packet_version": "old"},
        {"semantic_alignment": "correct"},
        {"confidence": 2.0},
    ):
        try:
            _annotation(packet, **changes).validate(packet)
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed annotation accepted: {changes}")


def test_provider_payload_cannot_create_attestation():
    record = _MODULE.HostVerificationRecord(
        "packet-a", "digest", "rubric", "source", "normalizer", "v1",
        _MODULE.VerificationStage.EVIDENCE_VERIFIED, "independent source", True,
    )
    try:
        _MODULE.attest_host_annotation(record)
    except ValueError as error:
        assert "provider" in str(error)
    else:
        raise AssertionError("provider payload created an attestation")


def test_attestation_requires_evidence_verified_stage():
    record = _MODULE.HostVerificationRecord(
        "packet-a", "digest", "rubric", "source", "normalizer", "v1",
        _MODULE.VerificationStage.OBSERVATION_MATCHED, "independent source",
    )
    try:
        _MODULE.attest_host_annotation(record)
    except ValueError as error:
        assert "verified" in str(error)
    else:
        raise AssertionError("unverified annotation was attested")


def test_valid_host_attestation_is_bound_to_annotation_digest():
    packet = _MODULE.make_blinded_packet(_case())
    annotation = _annotation(packet)
    annotation.validate(packet)
    digest = _MODULE.annotation_digest(annotation)
    record = _MODULE.HostVerificationRecord(
        packet.packet_id, digest, packet.rubric_version, "host-source", "host-normalizer", "v1",
        _MODULE.VerificationStage.EVIDENCE_VERIFIED, "independent source",
    )
    attestation = _MODULE.attest_host_annotation(record)
    assert attestation.annotation_digest == digest
    assert attestation.packet_id == packet.packet_id


def test_reviewer_disagreement_remains_visible_and_unadjudicated():
    packet = _MODULE.make_blinded_packet(_case())
    first = _annotation(packet, reviewer_alias="reviewer-a")
    second = _annotation(packet, reviewer_alias="reviewer-b", semantic_alignment="misaligned")
    summary = _MODULE.compare_reviewers((first, second))[0]
    assert summary["reviewer_count"] == 2
    assert summary["alignment_agreement"] is False
    assert summary["unresolved_disagreement"] is True
    assert summary["adjudicated"] is False
    assert len(summary["raw_judgments"]) == 2


def test_candidate_alias_cannot_claim_independent_kind():
    packet = _MODULE.make_blinded_packet(_case())
    record = _annotation(packet, reviewer_alias="candidate-a", annotation_kind=_MODULE.AnnotationKind.INDEPENDENT)
    try:
        record.validate(packet)
    except ValueError as error:
        assert "candidate" in str(error)
    else:
        raise AssertionError("candidate annotation claimed independence")


def test_annotation_manifest_keeps_provider_and_condition_data_private():
    path = Path(__file__).parents[3] / "docs" / "reports" / "pr62-annotation-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["raw_provider_payload_public"] is False
    assert manifest["condition_metadata_public"] is False
    assert manifest["automatic_adjudication"] is False
    assert manifest["provider_can_create_attestation"] is False
