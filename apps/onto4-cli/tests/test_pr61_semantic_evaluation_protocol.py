import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import sys


_PATH = Path(__file__).parents[1] / "research" / "pr61_semantic_evaluation_protocol.py"
_SPEC = importlib.util.spec_from_file_location("pr61_semantic_evaluation_protocol", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_protocol_corpus_has_two_families_and_disclosed_historical_fixtures():
    cases = _MODULE.corpus()
    assert len(cases) == 16
    assert {case.family for case in cases} == {"genome_identity", "intrinsic_time"}
    assert sum(case.previously_published for case in cases) == 4
    assert len(_MODULE.development_cases()) == 12
    assert all(case.case_id for case in cases)


def test_development_corpus_covers_all_required_classes():
    classes = {case.case_class.value for case in _MODULE.corpus() if not case.previously_published}
    assert classes == {
        "same_semantics_same_id",
        "same_semantics_different_id",
        "wrong_semantics_correct_id",
        "wrong_semantics_different_id",
        "genuinely_resolved_ambiguity",
        "merely_omitted_ambiguity",
        "unrelated_valid_refinement",
        "partial_clarification",
        "unsupported_ontological_assertion",
        "ambiguous_undecidable_successor",
        "contradictory_interpretation",
        "structurally_changed_equivalent",
    }


def test_holdout_manifest_marks_disclosed_fixtures_and_missing_private_holdout():
    manifest = _MODULE.holdout_manifest()
    assert manifest["private_holdout_size"] == 0
    assert manifest["private_holdout_ready"] is False
    assert manifest["disclosed_fixture_count"] == 4
    assert manifest["labels_published"] is True
    assert manifest["raw_text_published"] is True
    assert manifest["independent_gold_available"] is False
    assert len(manifest["disclosed_fixture_commitments"]) == 4
    assert all(len(commitment) == 64 for commitment in manifest["disclosed_fixture_commitments"])


def test_case_validation_rejects_empty_or_unknown_scope():
    case = _MODULE.corpus()[0]
    for field in ("case_id", "family", "initial_interpretation"):
        values = {field: ""}
        malformed = replace(case, **values)
        try:
            _MODULE.validate_case(malformed)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{field} was accepted empty")
    malformed = replace(case, case_id="other-01")
    try:
        _MODULE.validate_case(malformed)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown case scope was accepted")


def test_manifest_matches_deterministic_protocol_artifact():
    path = Path(__file__).parents[3] / "docs" / "reports" / "pr61-protocol-manifest.json"
    assert json.loads(path.read_text(encoding="utf-8")) == _MODULE.protocol_artifact()


def test_public_development_index_matches_fixture_cases():
    path = Path(__file__).parents[3] / "docs" / "reports" / "pr61-development-corpus.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    expected = [
        {
            "case_id": case.case_id,
            "family": case.family,
            "case_class": case.case_class.value,
            "target_key": case.intended_target_key,
            "observed_target_key": case.observed_successor_target_key,
            "observed_target_id": case.observed_successor_target_id,
            "alignment": case.expected_alignment.value,
            "resolution": case.expected_resolution.value,
            "evidence": case.expected_evidence.value,
        }
        for case in _MODULE.corpus()
        if not case.previously_published
    ]
    assert index["cases"] == expected
    assert index["labels_are_independent_gold"] is False


def test_annotation_schema_is_valid_json_and_redaction_safe():
    path = Path(__file__).parents[3] / "docs" / "reports" / "pr61-annotation-schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert "raw_content" not in schema["properties"]
    assert "provider_name" not in schema["properties"]
    assert "semantic_alignment" in schema["properties"]
