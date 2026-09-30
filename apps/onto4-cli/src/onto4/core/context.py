"""Assessment context and ontology profiles."""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import AtomicVerdictStore, EvidenceStore


@dataclass(frozen=True)
class PredicateSignature:
    domain: tuple[str, ...]
    returns: str = "Proposition"


@dataclass
class OntologyProfile:
    name: str = "default"
    types: dict[str, str] = field(default_factory=dict)
    predicates: dict[str, PredicateSignature] = field(default_factory=dict)
    type_parents: dict[str, tuple[str, ...]] = field(default_factory=dict)
    absent_concepts: set[str] = field(default_factory=set)

    def is_type_compatible(self, actual: str, expected: str) -> bool:
        if actual == expected:
            return True
        pending = list(self.type_parents.get(actual, ()))
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            if current == expected:
                return True
            seen.add(current)
            pending.extend(self.type_parents.get(current, ()))
        return False


@dataclass(frozen=True)
class SemanticProfile:
    name: str = "strict_onto4"
    strict: bool = True


@dataclass(frozen=True)
class EpistemicProfile:
    name: str = "supplied_evidence_only"


@dataclass(frozen=True)
class InferenceProfile:
    name: str = "direct_evidence"


@dataclass(frozen=True)
class Perspective:
    name: str = "default"


@dataclass
class AssessmentContext:
    ontology: OntologyProfile = field(default_factory=OntologyProfile)
    semantics: SemanticProfile = field(default_factory=SemanticProfile)
    epistemics: EpistemicProfile = field(default_factory=EpistemicProfile)
    inference: InferenceProfile = field(default_factory=InferenceProfile)
    perspective: Perspective = field(default_factory=Perspective)
    evidence: EvidenceStore = field(default_factory=EvidenceStore)
    verdicts: AtomicVerdictStore = field(default_factory=AtomicVerdictStore)
