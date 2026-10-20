"""Run the bounded PR #40 semantic-binding pilot.

The runner is intentionally research-only.  It compares one host-bound
Full Snapshot call with one explicit-binding call for each frozen case.  The
host owns snapshot IDs and admission; model claims are evidence to validate,
not authority to mutate an interpretation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from onto4.pipeline.semantic_binding import (
    BindingEvaluation,
    BindingTransition,
    PublicSemanticTarget,
    SemanticTargetCatalog,
    evaluate_binding_claim,
)
from onto4.providers import (
    OpenAICompatibleClient,
    OpenAICompatibleInterpretationProvider,
    ProviderProfile,
)
from onto4.providers.openai_adapters import (
    ProviderSchemaError,
    _parse_interpretation,
    _response_json,
)
from onto4.providers.protocols import InterpretationRequest
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    InterpretationSpace,
    OntologyCandidate,
)


SOURCE_SHA = "d969338ee040e304e4dc1afb0f3aa1a373604967"
PROMPT_VERSION = "pr40-semantic-binding-v2"


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    source_text: str
    target_id: str
    target_kind: ClarificationKind
    answer: str


CASES = (
    CaseSpec(
        "genome-identity-bounded",
        "Does sharing a genome make two people one person?",
        "ambiguity-genome",
        ClarificationKind.Meaning,
        "I mean numerical identity: they are one and the same individual.",
    ),
    CaseSpec(
        "intrinsic-time-bounded",
        "Does the sequence have an intrinsic present?",
        "ambiguity-present",
        ClarificationKind.Meaning,
        "I mean an observer-independent present in the sequence itself.",
    ),
)


CATALOGS = {
    "genome-identity-bounded": SemanticTargetCatalog(
        1,
        {
            "ambiguity-genome": PublicSemanticTarget(
                "ambiguity-genome", "Meaning", "meaning of genome sharing"
            ),
            "ambiguity-criterion": PublicSemanticTarget(
                "ambiguity-criterion", "Meaning", "identity criterion"
            ),
        },
    ),
    "intrinsic-time-bounded": SemanticTargetCatalog(
        1,
        {
            "ambiguity-present": PublicSemanticTarget(
                "ambiguity-present", "Meaning", "meaning of an intrinsic present"
            ),
            "ambiguity-observer": PublicSemanticTarget(
                "ambiguity-observer", "Ontology", "observer-independent time"
            ),
        },
    ),
}


def _initial(spec: CaseSpec) -> InterpretationSpace:
    return InterpretationSpace(
        id=f"{spec.case_id}-host-initial",
        source_text=spec.source_text,
        conceptual_depth=ConceptualDepth.Philosophical,
        ambiguities=(
            Ambiguity("ambiguity-0", spec.target_id, "host-bound fixture", spec.target_id),
        ),
        ontologies=(
            OntologyCandidate(
                "ontology-0",
                "observer-independent time",
                "host-bound fixture",
                "ambiguity-observer" if spec.case_id == "intrinsic-time-bounded" else None,
            ),
        ),
    )


def _question(spec: CaseSpec) -> ClarificationQuestion:
    return ClarificationQuestion(
        id=f"{spec.target_kind.value.lower()}:{spec.target_id}",
        kind=spec.target_kind,
        text="Clarify the host-issued semantic target.",
        target_ids=(spec.target_id,),
    )


def _projection(snapshot: InterpretationSpace) -> dict[str, Any]:
    return {
        "source_text": snapshot.source_text,
        "conceptual_depth": snapshot.conceptual_depth.value,
        "ambiguities": [
            {"term": item.term, "description": item.description, "target_id": item.target_id}
            for item in snapshot.ambiguities
        ],
        "presuppositions": [{"description": item.description} for item in snapshot.presuppositions],
        "ontologies": [
            {"label": item.label, "description": item.description, "target_id": item.target_id}
            for item in snapshot.ontologies
        ],
        "readings": [],
    }


def _target_present(snapshot: InterpretationSpace, target_id: str) -> bool:
    return any(
        item.target_id == target_id
        for item in (*snapshot.ambiguities, *snapshot.ontologies)
    )


def _evaluation_payload(evaluation: BindingEvaluation) -> dict[str, Any]:
    return {
        "schema": evaluation.schema.value,
        "catalog": evaluation.catalog.value,
        "lineage": evaluation.lineage.value,
        "transition": evaluation.transition.value,
        "semantic_identity": evaluation.semantic_identity.value,
        "structurally_admissible": evaluation.structurally_admissible,
        "errors": list(evaluation.errors),
    }


def _full_snapshot(
    client: OpenAICompatibleClient,
    spec: CaseSpec,
    initial: InterpretationSpace,
    question: ClarificationQuestion,
    catalog: SemanticTargetCatalog,
) -> tuple[InterpretationSpace, BindingEvaluation]:
    provider = OpenAICompatibleInterpretationProvider(client)
    provider._remember_target_catalog(
        initial,
        {
            target.id: {"kind": target.kind, "description": target.description}
            for target in catalog.targets.values()
        },
    )
    successor = provider.refine(initial, question, spec.answer)
    successor = replace(successor, id=f"{spec.case_id}-full-successor")
    no_binding = {
        "relation": "no_binding",
        "target_id": None,
        "target_kind": None,
        "source_target_id": None,
        "previous_snapshot_id": initial.id,
        "current_snapshot_id": successor.id,
    }
    evaluation = evaluate_binding_claim(
        no_binding,
        transition=BindingTransition(initial, successor, question),
        catalog=catalog,
    )
    return successor, evaluation


def _explicit_binding(
    client: OpenAICompatibleClient,
    spec: CaseSpec,
    initial: InterpretationSpace,
    question: ClarificationQuestion,
    catalog: SemanticTargetCatalog,
) -> tuple[InterpretationSpace, BindingEvaluation]:
    host_successor_id = f"{spec.case_id}-explicit-successor"
    public_catalog = {
        target.id: {"kind": target.kind, "description": target.description}
        for target in catalog.targets.values()
    }
    messages = (
        {"role": "system", "content": "Return only the requested JSON object."},
        {
            "role": "user",
            "content": (
                "Refine the current interpretation after the user's answer. Return exactly "
                "{successor, binding_claim}. The successor MUST have exactly these keys: "
                "source_text, conceptual_depth, ambiguities, presuppositions, ontologies, "
                "readings. Each ambiguity has exactly term, description, target_id (optional); "
                "each presupposition has exactly description; each ontology has exactly label, "
                "description, target_id (optional); each reading has exactly label, description "
                "and presupposition_indexes. Do not put term or target_id in presuppositions. "
                "The successor contains only source_text, "
                "conceptual_depth, ambiguities, presuppositions, ontologies and readings; "
                "do not invent object IDs. The binding_claim is a separate provider claim. "
                "Use relation anchored_update only when the same host target remains the "
                "object of the refinement; otherwise use no_binding. Do not infer a target "
                "from position. The host-issued target is the only allowed target. "
                f"Host previous_snapshot_id: {initial.id}. Host current_snapshot_id: {host_successor_id}. "
                f"Public target catalog: {json.dumps(public_catalog, ensure_ascii=False, sort_keys=True)}\n"
                f"Current interpretation: {json.dumps(_projection(initial), ensure_ascii=False, sort_keys=True)}\n"
                f"Question: {json.dumps({'kind': question.kind.value, 'target_ids': list(question.target_ids)}, ensure_ascii=False)}\n"
                f"Answer: {spec.answer}\n"
                "The binding_claim fields are relation, target_id, target_kind, "
                "source_target_id, previous_snapshot_id and current_snapshot_id."
            ),
        },
    )
    payload = _response_json(client, messages, stage="pr40-explicit-binding")
    successor_payload = payload.get("successor")
    claim_payload = payload.get("binding_claim")
    if not isinstance(successor_payload, dict) or not isinstance(claim_payload, dict):
        raise ProviderSchemaError("Explicit binding response requires successor and binding_claim objects.")
    parsed = _parse_interpretation(
        successor_payload,
        InterpretationRequest(
            initial.source_text,
            conceptual_depth=initial.conceptual_depth,
            state={"semantic_target_catalog": public_catalog},
        ),
    )
    successor = replace(parsed, id=host_successor_id)
    evaluation = evaluate_binding_claim(
        claim_payload,
        transition=BindingTransition(initial, successor, question),
        catalog=catalog,
    )
    return successor, evaluation


def run_case(client: OpenAICompatibleClient, spec: CaseSpec) -> dict[str, Any]:
    initial = _initial(spec)
    question = _question(spec)
    catalog = CATALOGS[spec.case_id]
    cells: list[dict[str, Any]] = []
    for condition, runner in (("full_snapshot", _full_snapshot), ("explicit_binding", _explicit_binding)):
        try:
            successor, evaluation = runner(client, spec, initial, question, catalog)
            cells.append(
                {
                    "condition": condition,
                    "provider_successor_valid": True,
                    "transition_provenance_valid": True,
                    "target_present_in_successor": _target_present(successor, spec.target_id),
                    "binding": _evaluation_payload(evaluation),
                }
            )
        except Exception as exc:
            cells.append(
                {
                    "condition": condition,
                    "provider_successor_valid": False,
                    "transition_provenance_valid": False,
                    "target_present_in_successor": None,
                    "outcome": getattr(exc, "code", type(exc).__name__),
                    "detail_code": getattr(exc, "code", type(exc).__name__),
                }
            )
    return {
        "case_id": spec.case_id,
        "question_kind": question.kind.value,
        "question_target_ids": list(question.target_ids),
        "host_workflow_admission": "not_evaluated",
        "semantic_oracle": "none",
        "cells": cells,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-label", default="bonsai2-27b-pq2_0")
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    args = parser.parse_args()
    profile = ProviderProfile(
        base_url=args.endpoint,
        model=args.model,
        max_output_tokens=args.max_output_tokens,
        temperature=0,
        disable_thinking=True,
        timeout_seconds=90,
    )
    client = OpenAICompatibleClient(profile)
    prompt_hash = hashlib.sha256(PROMPT_VERSION.encode("utf-8")).hexdigest()
    payload = {
        "record_type": "pr40_semantic_target_binding_pilot",
        "run_id": args.run_id,
        "source_sha": SOURCE_SHA,
        "model": args.model_label,
        "backend": "llama.cpp OpenAI-compatible /v1",
        "sampling": {
            "temperature": 0,
            "thinking_enabled": False,
            "max_output_tokens": args.max_output_tokens,
        },
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": prompt_hash,
        "semantic_oracle": None,
        "host_workflow_admission": "not_evaluated",
        "cases": [run_case(client, spec) for spec in CASES],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
