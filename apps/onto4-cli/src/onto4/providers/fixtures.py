"""Deterministic provider fixtures for the interpretation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from onto4.reasoning import ConceptualDepth, FormalizationCandidate, InterpretationSpace

from .protocols import (
    DecisionProfile,
    FormalizationRequest,
    InterpretationRequest,
    TypedDecision,
    TypedDecisionBatchProvider,
    TypedDecisionProvider,
    TypedDecisionRequest,
)


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


@dataclass(frozen=True)
class FixtureDecisionProvider(TypedDecisionProvider):
    """Return bounded decisions by exact question text for one profile."""

    profile: DecisionProfile
    decisions: Mapping[str, TypedDecision]

    def decide(self, request: TypedDecisionRequest) -> TypedDecision:
        if (
            request.profile != self.profile.id
            or request.profile_version != self.profile.version
            or request.choices != self.profile.choices
        ):
            raise ValueError(
                "Decision request does not match fixture profile "
                f"{self.profile.id!r} v{self.profile.version}."
            )
        try:
            decision = self.decisions[request.question]
        except KeyError as exc:
            raise KeyError(f"No decision fixture for question {request.question!r}.") from exc
        self.profile.validate(decision)
        return decision


@dataclass(frozen=True)
class FixtureBatchDecisionProvider(FixtureDecisionProvider, TypedDecisionBatchProvider):
    """Optional deterministic fan-out provider over a shared state."""

    def decide_many(
        self, requests: Sequence[TypedDecisionRequest]
    ) -> tuple[TypedDecision, ...]:
        return tuple(self.decide(request) for request in requests)
