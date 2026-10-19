"""Small reproducible runner for the PR #39 target-binding experiment.

This is research tooling, not an Onto4 admission rule.  It deliberately starts
from host-bound synthetic snapshots so that preservation can be measured without
silently treating model-generated positional IDs as semantic identity.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from onto4.pipeline.interactive import ModelClarificationPolicy
from onto4.providers import (
    OpenAICompatibleClient,
    OpenAICompatibleInterpretationProvider,
    ProviderProfile,
)
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    FixtureClarificationPolicy,
    InterpretationSpace,
    OntologyCandidate,
    SemanticReading,
)


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    source_text: str
    meaning_target: str
    meaning_answer: str
    second_kind: ClarificationKind
    second_target: str
    second_answer: str


CASES = (
    CaseSpec(
        "genome-identity-bounded",
        "Does sharing a genome make two people one person?",
        "ambiguity-genome",
        "I mean numerical identity: they are one and the same individual.",
        ClarificationKind.Meaning,
        "ambiguity-criterion",
        "No, two people can have the same genome and remain distinct individuals.",
    ),
    CaseSpec(
        "intrinsic-time-bounded",
        "Does the sequence have an intrinsic present?",
        "ambiguity-present",
        "I mean an observer-independent present in the sequence itself.",
        ClarificationKind.Ontology,
        "ambiguity-observer",
        "Yes, that is the intended assumption.",
    ),
)


CATALOGS: dict[str, dict[str, dict[str, str]]] = {
    "genome-identity-bounded": {
        "ambiguity-genome": {
            "kind": "Meaning",
            "description": "The meaning of sharing a genome in the user's claim.",
        },
        "ambiguity-criterion": {
            "kind": "Meaning",
            "description": "The criterion by which genome sharing would establish numerical identity.",
        },
    },
    "intrinsic-time-bounded": {
        "ambiguity-present": {
            "kind": "Meaning",
            "description": "The meaning of an intrinsic present in the sequence.",
        },
        "ambiguity-observer": {
            "kind": "Ontology",
            "description": "Whether the claim assumes observer-independent time rather than sequence order alone.",
        },
    },
}


def _initial_snapshot(spec: CaseSpec) -> InterpretationSpace:
    return InterpretationSpace(
        id=f"{spec.case_id}-host-bound-initial",
        source_text=spec.source_text,
        conceptual_depth=ConceptualDepth.Philosophical,
        ambiguities=(
            Ambiguity(
                "ambiguity-0",
                spec.meaning_target,
                "host-bound ambiguity fixture",
                spec.meaning_target,
            ),
        ),
        ontologies=(
            OntologyCandidate(
                "ontology-0",
                "observer-independent time",
                "host-bound ontology fixture",
                (
                    "ambiguity-observer"
                    if spec.case_id == "intrinsic-time-bounded"
                    else None
                ),
            ),
        ),
        readings=(SemanticReading("reading-0", "bounded reading", "fixture reading"),),
    )


def _snapshot_ids(snapshot: InterpretationSpace) -> dict[str, list[dict[str, str | None]]]:
    return {
        "ambiguities": [
            {"structural_id": item.id, "target_id": item.target_id}
            for item in snapshot.ambiguities
        ],
        "ontologies": [
            {"structural_id": item.id, "target_id": item.target_id}
            for item in snapshot.ontologies
        ],
    }


def _question(
    *,
    kind: ClarificationKind,
    target_id: str,
    structural_id: str,
) -> ClarificationQuestion:
    return ClarificationQuestion(
        id=f"{kind.value.lower()}:{target_id}",
        kind=kind,
        text="Clarify the host-issued semantic target.",
        target_ids=(target_id,),
        structural_target_ids=(structural_id,),
    )


def run_case(
    provider: OpenAICompatibleInterpretationProvider,
    spec: CaseSpec,
) -> dict[str, Any]:
    catalog = CATALOGS[spec.case_id]
    initial = _initial_snapshot(spec)
    # This is the same snapshot-bound registry used by the production adapter;
    # the experiment makes the binding explicit instead of deriving it from a
    # model response.
    provider._remember_target_catalog(initial, catalog)
    policy = ModelClarificationPolicy(FixtureClarificationPolicy(), provider)
    questions = (
        _question(
            kind=ClarificationKind.Meaning,
            target_id=spec.meaning_target,
            structural_id="ambiguity-0",
        ),
        _question(
            kind=spec.second_kind,
            target_id=spec.second_target,
            structural_id=("ambiguity-0" if spec.second_kind is ClarificationKind.Meaning else "ontology-0"),
        ),
    )
    answers = (spec.meaning_answer, spec.second_answer)
    current = initial
    turns: list[dict[str, Any]] = []
    for index, (question, answer) in enumerate(zip(questions, answers), start=1):
        try:
            successor, transition = policy.successor(
                interpretation=current,
                question=question,
                answer=answer,
            )
            if transition.previous_interpretation_id != current.id:
                raise ValueError("previous_interpretation_id mismatch")
            if transition.question_id != question.id:
                raise ValueError("question_id mismatch")
            if transition.successor_interpretation_id != successor.id:
                raise ValueError("successor_interpretation_id mismatch")
            expected = spec.meaning_target if index == 1 else spec.second_target
            observed = tuple(
                item.target_id
                for collection in (successor.ambiguities, successor.ontologies)
                for item in collection
                if item.target_id == expected
            )
            turns.append(
                {
                    "turn": index,
                    "question_kind": question.kind.value,
                    "question_target_ids": list(question.target_ids),
                    "parser_valid": True,
                    "host_admission": True,
                    "transition_provenance_valid": True,
                    "target_preserved": bool(observed),
                    "successor_target_ids": _snapshot_ids(successor),
                }
            )
            current = successor
        except Exception as exc:  # safe, per-turn diagnostic only
            turns.append(
                {
                    "turn": index,
                    "question_kind": question.kind.value,
                    "question_target_ids": list(question.target_ids),
                    "parser_valid": False,
                    "host_admission": False,
                    "transition_provenance_valid": False,
                    "target_preserved": None,
                    "error_code": type(exc).__name__,
                }
            )
            break
    return {
        "case_id": spec.case_id,
        "catalog_binding": "snapshot_bound_provider_registry",
        "synthetic_initial": _snapshot_ids(initial),
        "turns": turns,
        "accepted_turns": sum(item["host_admission"] for item in turns),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    args = parser.parse_args()
    profile = ProviderProfile(
        base_url=args.endpoint,
        model=args.model,
        max_output_tokens=args.max_output_tokens,
        temperature=0,
        timeout_seconds=60,
    )
    provider = OpenAICompatibleInterpretationProvider(OpenAICompatibleClient(profile))
    payload = {
        "record_type": "pr39_target_binding_experiment",
        "run_id": args.run_id,
        "protocol": "host_bound_two_turn_full_snapshot",
        "model": args.model,
        "sampling": {
            "temperature": 0,
            "thinking_enabled": False,
            "max_output_tokens": args.max_output_tokens,
        },
        "semantic_oracle": "none",
        "cases": [run_case(provider, spec) for spec in CASES],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
