"""Meta-level reasoning over multiple Onto4 formalization candidates."""

from .assessment import CandidateAssessment, assess_candidate, assess_candidates
from .candidates import FormalizationCandidate
from .cross_candidate import AssessmentLandscape, CrossCandidateStatus, aggregate_assessments
from .interpretation import (
    Ambiguity,
    ConceptualDepth,
    InterpretationSpace,
    OntologyCandidate,
    Presupposition,
    SemanticReading,
)

__all__ = [
    "Ambiguity",
    "AssessmentLandscape",
    "CandidateAssessment",
    "ConceptualDepth",
    "CrossCandidateStatus",
    "FormalizationCandidate",
    "InterpretationSpace",
    "OntologyCandidate",
    "Presupposition",
    "SemanticReading",
    "aggregate_assessments",
    "assess_candidate",
    "assess_candidates",
]
