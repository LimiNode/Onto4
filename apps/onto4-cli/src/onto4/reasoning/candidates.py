"""A formalization candidate remains distinct from its eventual assessment."""

from __future__ import annotations

from dataclasses import dataclass

from onto4.core.ast import Expr


@dataclass(frozen=True)
class FormalizationCandidate:
    """One explicit reading represented as an optional typed formalization.

    ``formalization=None`` is intentionally allowed while a reading has been
    identified but not yet expressed as an admitted formal proposition. That
    condition is meta-level unresolved, never an Onto4 ``U`` verdict.
    """

    id: str
    label: str
    # Candidate instance identity is distinct from this reusable formalization
    # identity, which permits one formalization to be assessed in many contexts.
    formalization_id: str
    context_id: str
    formalization: Expr | None
    reading_id: str | None = None
    assumptions: tuple[str, ...] = ()
