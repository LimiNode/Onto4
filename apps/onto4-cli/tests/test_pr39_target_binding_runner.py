from research.pr39_target_binding_runner import CASES, CATALOGS


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
