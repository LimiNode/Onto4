"""Deterministic consumers of bounded typed decisions."""

from __future__ import annotations

from dataclasses import dataclass

from .protocols import DecisionProfile, TypedDecision


@dataclass(frozen=True)
class DeterministicDecisionPolicy:
    """Consume a profile-scoped choice without assigning Onto4 semantics."""

    profile: DecisionProfile

    def select(self, decision: TypedDecision) -> str | None:
        self.profile.validate(decision)
        if decision.abstained or decision.choice is None:
            return None
        return decision.choice
