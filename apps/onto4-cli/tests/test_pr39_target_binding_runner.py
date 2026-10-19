from pathlib import Path

from research.pr39_target_binding_runner import CASES, CATALOGS
from onto4.pipeline.clarification_corpus import (
    load_clarification_corpus,
    load_semantic_target_catalog,
)


def test_pr39_fixture_targets_match_frozen_dialogue_protocol():
    by_case = {case.case_id: case for case in CASES}

    genome = by_case["genome-identity-bounded"]
    assert genome.meaning_target == "ambiguity-genome"
    assert genome.second_kind.value == "Meaning"
    assert genome.second_target == "ambiguity-criterion"
    assert set(CATALOGS[genome.case_id]) == {
        "ambiguity-genome",
        "ambiguity-criterion",
    }

    intrinsic_time = by_case["intrinsic-time-bounded"]
    assert intrinsic_time.meaning_target == "ambiguity-present"
    assert intrinsic_time.second_kind.value == "Ontology"
    assert intrinsic_time.second_target == "ambiguity-observer"
    assert set(CATALOGS[intrinsic_time.case_id]) == {
        "ambiguity-present",
        "ambiguity-observer",
    }


def test_pr39_fixture_targets_are_checked_against_real_frozen_yaml():
    root = Path(__file__).parents[1]
    corpus = load_clarification_corpus(
        root / "eval" / "clarification" / "bounded-dialogue-v1.yaml"
    )
    _version, catalog = load_semantic_target_catalog(
        root / "eval" / "clarification" / "bounded-dialogue-targets-v1.yaml"
    )
    cases = {case.case_id: case for case in corpus.cases}

    for spec in CASES:
        case = cases[spec.case_id]
        scripted = tuple(
            turn
            for turn in case.dialogue
            if turn.get("role") == "assistant" and "question_kind" in turn
        )
        assert len(scripted) == 2
        assert scripted[0]["question_kind"] == "Meaning"
        assert tuple(scripted[0]["target_ids"]) == (spec.meaning_target,)
        assert scripted[1]["question_kind"] == spec.second_kind.value
        assert tuple(scripted[1]["target_ids"]) == (spec.second_target,)
        assert set(CATALOGS[spec.case_id]) == set(catalog[spec.case_id])
        for turn in scripted:
            for target_id in turn["target_ids"]:
                assert catalog[spec.case_id][target_id]["kind"] == turn["question_kind"]
