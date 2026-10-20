from dataclasses import replace

import pytest

from onto4.pipeline import (
    BindingRelation,
    BindingTransition,
    CheckStatus,
    PublicSemanticTarget,
    SemanticIdentityStatus,
    SemanticTargetCatalog,
    evaluate_binding_claim,
    evaluate_binding_claims,
    parse_binding_claim,
)
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ConceptualDepth,
    ClarificationQuestion,
    InterpretationSpace,
    OntologyCandidate,
)


def _transition(*, two_targets: bool = False) -> BindingTransition:
    previous = InterpretationSpace(
        "snapshot-0",
        "A claim.",
        ConceptualDepth.Philosophical,
        ambiguities=(
            Ambiguity("a0", "identity", "old", target_id="target-a"),
            *(
                (Ambiguity("b0", "continuity", "old", target_id="target-b"),)
                if two_targets
                else ()
            ),
        ),
    )
    current = replace(
        previous,
        id="snapshot-1",
        ambiguities=tuple(
            replace(item, description=f"new:{item.description}")
            for item in previous.ambiguities
        ),
    )
    question = ClarificationQuestion(
        id="question-0",
        kind=ClarificationKind.Meaning,
        text="Clarify the meaning.",
        target_ids=("target-a", "target-b") if two_targets else ("target-a",),
    )
    return BindingTransition(previous, current, question)


def _catalog(*, include_second: bool = True) -> SemanticTargetCatalog:
    targets = {
        "target-a": PublicSemanticTarget("target-a", "Meaning", "identity"),
        "target-o": PublicSemanticTarget("target-o", "Ontology", "ontology"),
    }
    if include_second:
        targets["target-b"] = PublicSemanticTarget("target-b", "Meaning", "continuity")
    return SemanticTargetCatalog(1, targets)


def _claim(**overrides):
    payload = {
        "relation": "anchored_update",
        "target_id": "target-a",
        "target_kind": "Meaning",
        "source_target_id": "target-a",
        "previous_snapshot_id": "snapshot-0",
        "current_snapshot_id": "snapshot-1",
    }
    payload.update(overrides)
    return payload


def test_valid_anchored_update_keeps_semantic_identity_unverified():
    result = evaluate_binding_claim(
        _claim(), transition=_transition(), catalog=_catalog()
    )
    assert result.schema is CheckStatus.VALID
    assert result.catalog is CheckStatus.VALID
    assert result.lineage is CheckStatus.VALID
    assert result.transition is CheckStatus.VALID
    assert result.semantic_identity is SemanticIdentityStatus.UNVERIFIED
    assert result.structurally_admissible


def test_missing_target_id_is_schema_failure():
    result = evaluate_binding_claim(
        _claim(target_id=None), transition=_transition(), catalog=_catalog()
    )
    assert result.schema is CheckStatus.INVALID
    assert result.semantic_identity is SemanticIdentityStatus.UNVERIFIED


def test_unknown_target_id_fails_catalog_check():
    result = evaluate_binding_claim(
        _claim(target_id="unknown", source_target_id="unknown"),
        transition=_transition(),
        catalog=_catalog(),
    )
    assert result.schema is CheckStatus.VALID
    assert result.catalog is CheckStatus.INVALID
    assert result.transition is CheckStatus.INVALID


def test_wrong_but_valid_same_kind_target_fails_transition_check():
    result = evaluate_binding_claim(
        _claim(target_id="target-b", source_target_id="target-b"),
        transition=_transition(),
        catalog=_catalog(),
    )
    assert result.catalog is CheckStatus.VALID
    assert result.transition is CheckStatus.INVALID


def test_permuting_two_meaning_targets_is_rejected():
    result = evaluate_binding_claim(
        _claim(target_id="target-b", source_target_id="target-a"),
        transition=_transition(two_targets=True),
        catalog=_catalog(),
    )
    assert result.schema is CheckStatus.VALID
    assert result.transition is CheckStatus.INVALID


def test_cross_kind_binding_is_rejected_even_for_known_id():
    result = evaluate_binding_claim(
        _claim(target_id="target-o", target_kind="Ontology", source_target_id="target-o"),
        transition=_transition(),
        catalog=_catalog(),
    )
    assert result.catalog is CheckStatus.INVALID
    assert result.transition is CheckStatus.INVALID


def test_duplicate_binding_claims_are_rejected_together():
    results = evaluate_binding_claims(
        [_claim(), _claim(relation="preserve")],
        transition=_transition(),
        catalog=_catalog(),
    )
    assert len(results) == 2
    assert all(item.transition is CheckStatus.INVALID for item in results)
    assert all("Duplicate" in " ".join(item.errors) for item in results)


def test_stale_snapshot_lineage_is_rejected():
    result = evaluate_binding_claim(
        _claim(previous_snapshot_id="stale"),
        transition=_transition(),
        catalog=_catalog(),
    )
    assert result.lineage is CheckStatus.INVALID
    assert not result.structurally_admissible


def test_semantic_text_change_does_not_become_verified():
    transition = _transition()
    changed = replace(
        transition.current,
        ambiguities=(Ambiguity("a1", "identity", "unrelated new meaning", target_id="target-a"),),
    )
    result = evaluate_binding_claim(
        _claim(),
        transition=BindingTransition(transition.previous, changed, transition.question),
        catalog=_catalog(),
    )
    assert result.transition is CheckStatus.VALID
    assert result.semantic_identity is SemanticIdentityStatus.UNVERIFIED


def test_create_cannot_inherit_an_existing_target_id():
    result = evaluate_binding_claim(
        _claim(relation="create"), transition=_transition(), catalog=_catalog()
    )
    assert result.transition is CheckStatus.INVALID


def test_no_binding_is_explicit_non_comparable_outcome():
    result = evaluate_binding_claim(
        _claim(
            relation="no_binding",
            target_id=None,
            target_kind=None,
            source_target_id=None,
        ),
        transition=_transition(),
        catalog=_catalog(),
    )
    assert result.schema is CheckStatus.VALID
    assert result.semantic_identity is SemanticIdentityStatus.NOT_COMPARABLE
    assert not result.structurally_admissible


def test_private_oracle_fields_are_not_accepted_in_model_claim():
    with pytest.raises(ValueError, match="Unknown binding claim fields"):
        parse_binding_claim({**_claim(), "expected_intent": "private"})


def test_ontology_target_is_admissible_for_ontology_question():
    transition = _transition()
    ontology_previous = replace(
        transition.previous,
        ambiguities=(),
        ontologies=(OntologyCandidate("o0", "substance", "old", target_id="target-o"),),
    )
    ontology_current = replace(
        transition.current,
        ambiguities=(),
        ontologies=(OntologyCandidate("o1", "substance", "new", target_id="target-o"),),
    )
    question = replace(
        transition.question,
        kind=ClarificationKind.Ontology,
        target_ids=("target-o",),
    )
    result = evaluate_binding_claim(
        _claim(target_id="target-o", target_kind="Ontology", source_target_id="target-o"),
        transition=BindingTransition(ontology_previous, ontology_current, question),
        catalog=_catalog(),
    )
    assert result.structurally_admissible
