"""Deterministic provider fixtures for the interpretation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from onto4.reasoning import ConceptualDepth, FormalizationCandidate, InterpretationSpace

from .protocols import FormalizationRequest, InterpretationRequest


@dataclass(frozen=True)
class FixtureInterpretationProvider:
    """Return a predefined space for an exact source/depth routing key."""

    spaces: Mapping[tuple[str, ConceptualDepth | None], InterpretationSpace]

    def interpret(self, request: InterpretationRequest) -> InterpretationSpace:
        try:
            return self.spaces[(request.source_text, request.conceptual_depth)]
        except KeyError as exc:
            raise KeyError(
                "No interpretation fixture for source/depth "
                f"({request.source_text!r}, {request.conceptual_depth!r})."
            ) from exc


@dataclass(frozen=True)
class FixtureFormalizationProvider:
    """Return predefined candidates keyed by an interpretation identity."""

    candidates: Mapping[str, tuple[FormalizationCandidate, ...]]

    def formalize(self, request: FormalizationRequest) -> tuple[FormalizationCandidate, ...]:
        try:
            candidates = self.candidates[request.interpretation.id]
        except KeyError as exc:
            raise KeyError(
                "No formalization fixture for interpretation "
                f"{request.interpretation.id!r}."
            ) from exc
        reading_ids = {reading.id for reading in request.interpretation.readings}
        for candidate in candidates:
            if candidate.reading_id is not None and candidate.reading_id not in reading_ids:
                raise ValueError(
                    f"Candidate {candidate.id!r} refers to unknown reading "
                    f"{candidate.reading_id!r} in interpretation "
                    f"{request.interpretation.id!r}."
                )
        return candidates
