"""YAML loading kept outside the deterministic core."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from onto4.core import (
    And,
    AssessmentContext,
    Equivalent,
    EpistemicProfile,
    Implies,
    InferenceProfile,
    Not,
    OntologyProfile,
    Or,
    Perspective,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    SemanticProfile,
    Term,
)
from onto4.core.evidence import EvidenceStore, TruthStore, parse_evidence, parse_truth


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}.")
    return data


def _term(value: Any) -> Term:
    if isinstance(value, str):
        return Term(value)
    if isinstance(value, dict) and "name" in value:
        return Term(str(value["name"]), value.get("type"))
    raise ValueError(f"Invalid term: {value!r}")


def expression_from_mapping(data: Any):
    if not isinstance(data, dict):
        raise ValueError(f"Expression must be a YAML mapping: {data!r}")
    if "predicate" in data:
        args = tuple(_term(value) for value in data.get("args", ()))
        return PredicateExpr(PredicateCall(str(data["predicate"]), args))
    op = str(data.get("op", "")).lower()
    args = data.get("args", ())
    if op == "not" and len(args) == 1:
        return Not(expression_from_mapping(args[0]))
    binary = {"and": And, "or": Or, "implies": Implies, "equivalent": Equivalent}
    if op in binary and len(args) == 2:
        return binary[op](expression_from_mapping(args[0]), expression_from_mapping(args[1]))
    raise ValueError(f"Invalid expression mapping: {data!r}")


_ATOM_RE = re.compile(r"^\s*([A-Za-z_][\w.-]*)\s*\((.*)\)\s*$")


def expression_from_text(text: str) -> PredicateExpr:
    match = _ATOM_RE.match(text)
    if not match:
        raise ValueError(f"Only simple predicate evidence keys are supported: {text!r}")
    raw_args = match.group(2).strip()
    args = tuple(Term(item.strip()) for item in raw_args.split(",")) if raw_args else ()
    return PredicateExpr(PredicateCall(match.group(1), args))


def load_formalization(path: str | Path):
    data = _read_yaml(Path(path))
    return expression_from_mapping(data.get("expression", data))


def load_context(path: str | Path) -> AssessmentContext:
    source = Path(path)
    data = _read_yaml(source)
    ontology_data = data.get("ontology", {})
    predicates: dict[str, PredicateSignature] = {}
    for name, raw_signature in ontology_data.get("predicates", {}).items():
        if isinstance(raw_signature, list):
            domain = tuple(str(item) for item in raw_signature)
            returns = "Proposition"
        else:
            raw_signature = raw_signature or {}
            domain = tuple(str(item) for item in raw_signature.get("domain", ()))
            returns = str(raw_signature.get("returns", "Proposition"))
        predicates[str(name)] = PredicateSignature(domain=domain, returns=returns)

    raw_evidence = data.get("evidence", data.get("facts", {})) or {}
    entries: dict[str, Any] = {}
    if isinstance(raw_evidence, dict):
        entries = raw_evidence
    elif isinstance(raw_evidence, list):
        for item in raw_evidence:
            if not isinstance(item, dict):
                raise ValueError(f"Invalid evidence item in {source}: {item!r}")
            key = item.get("expression")
            if key is None and "predicate" in item:
                key = f"{item['predicate']}({', '.join(str(arg) for arg in item.get('args', ()))})"
            if key is None:
                raise ValueError(f"Evidence item has no expression in {source}: {item!r}")
            entries[str(key)] = item.get("supports", item.get("value"))
    evidence = EvidenceStore()
    for key, value in entries.items():
        expr = expression_from_text(str(key))
        evidence.entries[expr.call.key()] = parse_evidence(value)

    raw_truth = data.get("truth", {}) or {}
    if not isinstance(raw_truth, dict):
        raise ValueError(f"Truth must be a mapping in {source}.")
    truth = TruthStore()
    for key, value in raw_truth.items():
        expr = expression_from_text(str(key))
        truth.entries[expr.call.key()] = parse_truth(value)

    return AssessmentContext(
        ontology=OntologyProfile(
            name=str(data.get("name", source.stem)),
            types={str(key): str(value) for key, value in ontology_data.get("types", {}).items()},
            predicates=predicates,
            type_parents={
                str(key): tuple(str(item) for item in value)
                for key, value in ontology_data.get("type_parents", {}).items()
            },
            absent_concepts={str(item) for item in ontology_data.get("absent_concepts", ())},
        ),
        semantics=SemanticProfile(
            name=str(data.get("semantics", {}).get("name", "strict_onto4")),
            strict=bool(data.get("semantics", {}).get("strict", True)),
        ),
        epistemics=EpistemicProfile(name=str(data.get("epistemics", {}).get("name", "supplied_evidence_only"))),
        inference=InferenceProfile(name=str(data.get("inference", {}).get("name", "direct_evidence"))),
        perspective=Perspective(name=str(data.get("perspective", {}).get("name", "default"))),
        evidence=evidence,
        truth=truth,
    )
