"""Bounded, non-authoritative projections supplied to formalization models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from onto4.core import AssessmentContext


@dataclass(frozen=True)
class PredicateProjection:
    name: str
    domain: tuple[str, ...]
    returns: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": list(self.domain),
            "returns": self.returns,
        }


@dataclass(frozen=True)
class AssessmentContextProjection:
    """The ontology affordances visible to a model-backed formalizer.

    Evidence, verdict stores, epistemic settings and other assessment inputs
    are intentionally absent. This projection describes what expressions may
    be formed, not what Onto4 should conclude about them.
    """

    id: str
    ontology: str
    symbols: tuple[tuple[str, str], ...] = ()
    predicates: tuple[PredicateProjection, ...] = ()
    type_parents: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Context projection id must not be empty.")
        if not self.ontology.strip():
            raise ValueError("Context projection ontology must not be empty.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ontology": self.ontology,
            "symbols": [
                {"name": name, "type": declared_type}
                for name, declared_type in self.symbols
            ],
            "predicates": [predicate.as_dict() for predicate in self.predicates],
            "type_parents": [
                {"type": name, "parents": list(parents)}
                for name, parents in self.type_parents
            ],
        }


def project_assessment_context(
    context_id: str,
    context: AssessmentContext,
) -> AssessmentContextProjection:
    """Create a stable ontology-only snapshot from an assessment context."""

    ontology = context.ontology
    return AssessmentContextProjection(
        id=context_id,
        ontology=ontology.name,
        symbols=tuple(sorted((str(name), str(value)) for name, value in ontology.types.items())),
        predicates=tuple(
            PredicateProjection(
                name=str(name),
                domain=tuple(signature.domain),
                returns=signature.returns,
            )
            for name, signature in sorted(ontology.predicates.items())
        ),
        type_parents=tuple(
            sorted((str(name), tuple(parents)) for name, parents in ontology.type_parents.items())
        ),
    )


__all__ = [
    "AssessmentContextProjection",
    "PredicateProjection",
    "project_assessment_context",
]
