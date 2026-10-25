import json
from pathlib import Path


def test_pr54_synthesis_is_conservative_and_non_semantic():
    path = (
        Path(__file__).parents[3]
        / "docs"
        / "reports"
        / "pr54-evidence-synthesis.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["overall_verdict"] == "not_comparable"
    assert payload["semantic_identity"] == "not_evaluated"
    assert payload["architectural_decision"] == "investigate_provider_target_binding_independently"
    assert payload["production_admission_changed"] is False
    assert payload["semantic_adjudication_receipt_created"] is False
    assert payload["integration_status"]["merged_prs"] == [49, 50, 51, 52, 53, 54]
    assert payload["integration_status"]["open_draft_prs"] == [39]
    assert payload["matched_contract"]["current_version"] == "pr51-matched-clarification-v2"
    assert payload["matched_contract"]["historical_receipt_version"] == "pr51-matched-clarification-v1"
    assert payload["matched_contract"]["provider_context_independently_verified"] is False
    stages = {item["stage"]: item for item in payload["evidence"]}
    assert stages["pr50"]["result"] == "independent_host_contract_verification"
    assert stages["pr51"]["matched"] is True
    assert stages["pr52"]["result"] == "classifier_and_policy_integration_gates_passed"
    assert stages["pr53"]["matched"] is False


def test_pr54_does_not_claim_live_semantic_success():
    text = (
        Path(__file__).parents[3]
        / "docs"
        / "reports"
        / "pr54-evidence-synthesis.md"
    ).read_text(encoding="utf-8")

    assert "not_comparable" in text
    assert "initial_matched_continuation_not_comparable" in text
    assert "PR #49–#54" in text
    assert "semantic_identity" in text
    assert "не оправдывают production promotion" in text
