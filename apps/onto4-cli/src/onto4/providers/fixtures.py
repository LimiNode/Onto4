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
            return self.spaces[request.source_text]
        except KeyError as exc:
            raise KeyError(
                f"No interpretation fixture for source text {request.source_text!r}."
            ) from exc


@dataclass(frozen=True)
class FixtureFormalizationProvider:
    """Return predefined candidates keyed by a space's source text."""

    candidates: Mapping[str, tuple[FormalizationCandidate, ...]]

    def formalize(self, request: FormalizationRequest) -> tuple[FormalizationCandidate, ...]:
        try:
            return self.candidates[request.interpretation.source_text]
        except KeyError as exc:
            raise KeyError(
                "No formalization fixture for source text "
                f"{request.interpretation.source_text!r}."
            ) from exc
