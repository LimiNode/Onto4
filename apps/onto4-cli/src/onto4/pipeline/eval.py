"""File-based evaluation service used by the CLI."""

from __future__ import annotations

from pathlib import Path

from onto4.core import AssessmentResult, evaluate

from .loaders import load_context, load_formalization


def evaluate_files(formalization: str | Path, context: str | Path) -> AssessmentResult:
    return evaluate(load_formalization(formalization), load_context(context))
