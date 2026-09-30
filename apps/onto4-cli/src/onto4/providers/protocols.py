"""Dependency-inversion boundaries for future LLM and KEV adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class TypedDecisionRequest:
    profile: str
    question: str
    choices: tuple[str, ...]
    state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TypedDecision:
    choice: str
    confidence: float | None = None
    probabilities: Mapping[str, float] = field(default_factory=dict)


class TypedDecisionProvider(Protocol):
    """A bounded decision service; it does not define Onto4 semantics."""

    def decide(self, request: TypedDecisionRequest) -> TypedDecision:
        ...
