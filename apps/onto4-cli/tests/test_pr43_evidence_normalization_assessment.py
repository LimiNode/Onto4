import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[3]
ASSESSMENT = ROOT / "docs/reports/pr43-independent-evidence-normalization-assessment.json"


def test_pr43_assessment_is_reproducible_and_does_not_upgrade_pr40():
    assessment = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
    assert assessment["scope"] == "public_redacted_pr40_artifacts_only"
    assert assessment["model_run_started"] is False
    assert assessment["historical_receipts_rewritten"] is False
    assert assessment["production_admission_changed"] is False
    assert assessment["normalization_records_created"] == 0
    assert assessment["adjudication_receipts_created"] == 0
    assert assessment["semantic_identity_upgrade"] == "none"
    for source in assessment["sources"]:
        artifact = ROOT / source["path"]
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert source["sha256"] == digest
        assert source["status"] == "insufficient_evidence"
        assert source["missing"] == [
            "successor_snapshot_content",
            "previous_snapshot_id",
            "current_snapshot_id",
            "normalized_commitments",
        ]
