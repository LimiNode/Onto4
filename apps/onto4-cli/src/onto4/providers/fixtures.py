"""Deterministic provider fixtures for the interpretation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from onto4.reasoning import FormalizationCandidate, InterpretationSpace

from .protocols import FormalizationRequest, InterpretationRequest


@dataclass(frozen=True)
class FixtureInterpretationProvider:
    """Return a predefined interpretation space for exact source text."""

    spaces: Mapping[str, InterpretationSpace]

    def interpret(self, request: InterpretationRequest) -> InterpretationSpace:
        try:
            space = self.spaces[request.source_text]
        except KeyError as exc:
            raise KeyError(
                f"No interpretation fixture for source text {request.source_text!r}."
            ) from exc
        if request.conceptual_depth is not None and space.conceptual_depth is not request.conceptual_depth:
            raise ValueError(
                f"Interpretation fixture {space.id!r} has depth "
                f"{space.conceptual_depth.value!r}, not the requested "
                f"{request.conceptual_depth.value!r}."
            )
        return space


@dataclass(frozen=True)
class FixtureFormalizationProvider:
    """Return predefined candidates keyed by an interpretation identity."""

    candidates: Mapping[str, tuple[FormalizationCandidate, ...]]

    def formalize(self, request: FormalizationRequest) -> tuple[FormalizationCandidate, ...]:
        try:
            return self.candidates[request.interpretation.id]
        except KeyError as exc:
            raise KeyError(
                "No formalization fixture for interpretation "
                f"{request.interpretation.id!r}."
            ) from exc
