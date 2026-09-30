"""Public package for the experimental Onto4 CLI and kernel."""

from .core import (
    AssessmentContext,
    AssessmentResult,
    Evidence4,
    Verdict,
    evaluate,
)

__all__ = [
    "AssessmentContext",
    "AssessmentResult",
    "Evidence4",
    "Verdict",
    "evaluate",
]
