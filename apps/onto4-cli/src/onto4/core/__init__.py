"""Deterministic Onto4 domain model and evaluator."""

from .ast import (
    And,
    Equivalent,
    Implies,
    Not,
    PredicateCall,
    PredicateExpr,
    Term,
    Or,
)
from .context import (
    AssessmentContext,
    EpistemicProfile,
    InferenceProfile,
    OntologyProfile,
    Perspective,
    PredicateSignature,
    SemanticProfile,
)
from .evaluator import AssessmentResult, evaluate
from .values import Evidence4, SemanticStatus, Verdict

__all__ = [
    "And",
    "AssessmentContext",
    "AssessmentResult",
    "EpistemicProfile",
    "Equivalent",
    "Evidence4",
    "InferenceProfile",
    "Implies",
    "Not",
    "OntologyProfile",
    "Or",
    "Perspective",
    "PredicateCall",
    "PredicateExpr",
    "PredicateSignature",
    "SemanticProfile",
    "SemanticStatus",
    "Term",
    "Verdict",
    "evaluate",
]
