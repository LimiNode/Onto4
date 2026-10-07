"""Meta-level reasoning over multiple Onto4 formalization candidates."""

from .assessment import CandidateAssessment, assess_candidate, assess_candidates
from .candidates import FormalizationCandidate
from .clarification import (
    ClarificationContext,
    ClarificationKind,
    ClarificationPolicy,
    ClarificationQuestion,
    ClarificationState,
    ClarificationTurn,
    FixtureClarificationPolicy,
    has_discriminating_reading_provenance,
    KindAwareClarificationPolicy,
)
from .cross_candidate import AssessmentLandscape, CrossCandidateStatus, aggregate_assessments
from .disposition import PipelineDisposition
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
    "ClarificationContext",
    "ClarificationKind",
    "ClarificationPolicy",
    "ClarificationQuestion",
    "ClarificationState",
    "ClarificationTurn",
    "ConceptualDepth",
    "CrossCandidateStatus",
    "FormalizationCandidate",
    "InterpretationSpace",
    "OntologyCandidate",
    "PipelineDisposition",
    "Presupposition",
    "SemanticReading",
    "FixtureClarificationPolicy",
    "KindAwareClarificationPolicy",
    "has_discriminating_reading_provenance",
    "aggregate_assessments",
    "assess_candidate",
    "assess_candidates",
]
