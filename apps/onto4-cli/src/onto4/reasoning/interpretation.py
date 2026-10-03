"""Structures that preserve ambiguity before formalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ConceptualDepth(str, Enum):
    Ordinary = "ordinary"
    Reflective = "reflective"
    Philosophical = "philosophical"
    OntologySensitive = "ontology_sensitive"


@dataclass(frozen=True)
class Ambiguity:
    id: str
    term: str
    description: str


@dataclass(frozen=True)
class Presupposition:
    id: str
    description: str


@dataclass(frozen=True)
class OntologyCandidate:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class SemanticReading:
    id: str
    label: str
    description: str
    presupposition_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class InterpretationSpace:
    """Interpretations exposed before a natural-language question is formalized.

    This is meta-level data: it records possible readings and their assumptions.
    It carries no Onto4 verdict and does not select one reading as canonical.
    """

    id: str
    source_text: str
    conceptual_depth: ConceptualDepth
    ambiguities: tuple[Ambiguity, ...] = ()
    presuppositions: tuple[Presupposition, ...] = ()
    ontologies: tuple[OntologyCandidate, ...] = ()
    readings: tuple[SemanticReading, ...] = ()
