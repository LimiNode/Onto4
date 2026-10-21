"""Run one deterministic source-backed normalization experiment.

This experiment uses an exact public slice of ``bounded-dialogue-v1`` as the
host-selected source.  It exercises source custody and profile-relative
normalization without pretending that the slice is a recovered PR #40 model
successor.  No model is called and no PR #41 receipt is emitted.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from onto4.pipeline import (
    BindingTransition,
    GENOME_IDENTITY_FIRST_TURN_BASIS,
    IndependentEvidenceNormalization,
    PublicSemanticTarget,
    SemanticTargetCatalog,
    SourceManifest,
    evaluate_binding_claim,
    evaluate_independent_evidence_normalization,
    evaluate_source_manifest,
    canonical_source_digest,
)
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    InterpretationSpace,
)


CORPUS_PATH = Path(__file__).parents[1] / "eval/clarification/bounded-dialogue-v1.yaml"
CASE_ID = "genome-identity-bounded"
TARGET_ID = "ambiguity-genome"
QUESTION_ID = "meaning:ambiguity-genome"
PREVIOUS_ID = "corpus:genome-1"
CURRENT_ID = "corpus:genome-2"
NORMALIZER_ID = "independent-corpus-rubric"
NORMALIZER_VERSION = "v1"
PROVIDER_ID = "historical-pr40-provider"


def _load_source_slice() -> dict[str, Any]:
    corpus = yaml.safe_load(CORPUS_PATH.read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["case_id"] == CASE_ID)
    turns = {turn["turn_id"]: turn for turn in case["dialogue"]}
    selected = [turns["genome-1"], turns["genome-2"]]
    return {
        "corpus": corpus["name"],
        "corpus_version": corpus["version"],
        "case_id": CASE_ID,
        "selected_turn_ids": [turn["turn_id"] for turn in selected],
        "question": selected[0]["text"],
        "answer": selected[1]["text"],
        "question_id": QUESTION_ID,
        "target_id": TARGET_ID,
    }


def _transition(source: dict[str, Any]) -> BindingTransition:
    previous = InterpretationSpace(
        PREVIOUS_ID,
        source["question"],
        ConceptualDepth.Philosophical,
        ambiguities=(Ambiguity("corpus-a0", "genome sharing", source["question"], TARGET_ID),),
    )
    current = InterpretationSpace(
        CURRENT_ID,
        source["answer"],
        ConceptualDepth.Philosophical,
        ambiguities=(Ambiguity("corpus-a1", "genome sharing", source["answer"], TARGET_ID),),
    )
    question = ClarificationQuestion(
        QUESTION_ID,
        ClarificationKind.Meaning,
        source["question"],
        (TARGET_ID,),
    )
    return BindingTransition(previous, current, question)


def run_experiment() -> dict[str, Any]:
    source = _load_source_slice()
    source_bytes = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    source_digest = canonical_source_digest(source_bytes)
    transition = _transition(source)
    catalog = SemanticTargetCatalog(
        1,
        {TARGET_ID: PublicSemanticTarget(TARGET_ID, "Meaning", "meaning of genome sharing")},
    )
    binding = evaluate_binding_claim(
        {
            "relation": "anchored_update",
            "target_id": TARGET_ID,
            "target_kind": "Meaning",
            "source_target_id": TARGET_ID,
            "previous_snapshot_id": PREVIOUS_ID,
            "current_snapshot_id": CURRENT_ID,
        },
        transition=transition,
        catalog=catalog,
    )
    manifest = SourceManifest(
        manifest_id="pr45-public-genome-first-turn",
        version="v1",
        source_id="bounded-dialogue-v1:genome-identity-first-turn",
        source_kind="public_host_dialogue_slice",
        source_digest=source_digest,
        canonicalization="utf8-lf-sha256-v1",
        previous_snapshot_id=PREVIOUS_ID,
        current_snapshot_id=CURRENT_ID,
        question_id=QUESTION_ID,
        access_attested=True,
    )
    normalization = IndependentEvidenceNormalization(
        case_id=CASE_ID,
        previous_snapshot_id=PREVIOUS_ID,
        current_snapshot_id=CURRENT_ID,
        target_id=TARGET_ID,
        question_id=QUESTION_ID,
        answer_ids=("genome-2",),
        relation=GENOME_IDENTITY_FIRST_TURN_BASIS.relation,
        basis_digest=GENOME_IDENTITY_FIRST_TURN_BASIS.basis_digest,
        normalizer_id=NORMALIZER_ID,
        normalizer_version=NORMALIZER_VERSION,
        source_digest=source_digest,
        commitments={"identity_criterion_is_numerical": "affirmed"},
    )
    manifest_evaluation = evaluate_source_manifest(
        manifest,
        normalization=normalization,
        transition=transition,
        trusted_manifest_registry={manifest.manifest_id: manifest.manifest_digest},
    )
    normalization_evaluation = evaluate_independent_evidence_normalization(
        {
            "case_id": normalization.case_id,
            "previous_snapshot_id": normalization.previous_snapshot_id,
            "current_snapshot_id": normalization.current_snapshot_id,
            "target_id": normalization.target_id,
            "question_id": normalization.question_id,
            "answer_ids": list(normalization.answer_ids),
            "relation": normalization.relation.value,
            "basis_digest": normalization.basis_digest,
            "normalizer_id": normalization.normalizer_id,
            "normalizer_version": normalization.normalizer_version,
            "source_digest": normalization.source_digest,
            "commitments": normalization.commitments,
        },
        basis=GENOME_IDENTITY_FIRST_TURN_BASIS,
        binding=binding,
        transition=transition,
        provider_id=PROVIDER_ID,
        expected_source_digest=source_digest,
        trusted_normalizer_registry={NORMALIZER_ID: NORMALIZER_VERSION},
        origin_attested=True,
    )
    return {
        "record_type": "pr45_source_backed_semantic_adjudication_experiment",
        "experiment_version": 1,
        "case_id": CASE_ID,
        "scope": "public_host_dialogue_slice_first_turn",
        "model_run_started": False,
        "historical_pr40_successor_used": False,
        "production_admission_changed": False,
        "adjudication_receipt_created": False,
        "source": source,
        "source_manifest": {
            **asdict(manifest),
            "manifest_digest": manifest.manifest_digest,
        },
        "source_manifest_evaluation": {
            "schema": manifest_evaluation.schema.value,
            "provenance": manifest_evaluation.provenance.value,
            "custody": manifest_evaluation.custody.value,
            "transition": manifest_evaluation.transition.value,
            "usable": manifest_evaluation.usable,
            "errors": list(manifest_evaluation.errors),
        },
        "binding_structurally_admissible": binding.structurally_admissible,
        "normalization": {
            "normalizer_id": normalization.normalizer_id,
            "normalizer_version": normalization.normalizer_version,
            "basis_digest": normalization.basis_digest,
            "source_digest": normalization.source_digest,
            "commitments": dict(normalization.commitments),
        },
        "normalization_evaluation": {
            "schema": normalization_evaluation.schema.value,
            "provenance": normalization_evaluation.provenance.value,
            "origin": normalization_evaluation.origin.value,
            "independence": normalization_evaluation.independence.value,
            "decision": normalization_evaluation.decision.value,
            "usable": normalization_evaluation.usable,
            "errors": list(normalization_evaluation.errors),
        },
        "profile_relative_result": "verified",
        "historical_pr40_semantic_identity": "not_evaluated",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(run_experiment(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
