"""Dependency-inversion boundaries for future LLM and KEV adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from onto4.reasoning import FormalizationCandidate, InterpretationSpace


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


@dataclass(frozen=True)
class InterpretationRequest:
    """Input accepted by an interpretation provider."""

    source_text: str
    state: Mapping[str, Any] = field(default_factory=dict)


class InterpretationProvider(Protocol):
    """Expose ambiguity and readings without selecting an Onto4 verdict."""

    def interpret(self, request: InterpretationRequest) -> InterpretationSpace:
        ...


@dataclass(frozen=True)
class FormalizationRequest:
    """Request to turn an interpretation space into explicit candidates."""

    interpretation: InterpretationSpace
    state: Mapping[str, Any] = field(default_factory=dict)


class FormalizationProvider(Protocol):
    """Produce candidates; assessment remains a separate deterministic step."""

    def formalize(self, request: FormalizationRequest) -> Sequence[FormalizationCandidate]:
        ...
