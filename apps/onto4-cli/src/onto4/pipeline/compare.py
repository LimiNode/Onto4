"""Evaluate one formalization under several contexts."""

from __future__ import annotations

from pathlib import Path

from onto4.core import AssessmentResult, evaluate

from .loaders import load_context, load_formalization


def compare_files(formalization: str | Path, contexts: list[str | Path]) -> list[tuple[str, AssessmentResult]]:
    expr = load_formalization(formalization)
    return [(str(path), evaluate(expr, load_context(path))) for path in contexts]
