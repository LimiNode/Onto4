"""Dependency-inversion boundaries for future LLM and KEV adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from onto4.reasoning import ConceptualDepth, FormalizationCandidate, InterpretationSpace


@dataclass(frozen=True)
class TypedDecisionRequest:
    profile: str
    question: str
    choices: tuple[str, ...]
    state: Mapping[str, Any] = field(default_factory=dict)
    profile_version: str | None = None


@dataclass(frozen=True)
class TypedDecision:
    """A profile-provenanced bounded decision or explicit abstention."""

    profile_id: str
    profile_version: str
    choice: str | None = None
    abstained: bool = False
    confidence: float | None = None
    probabilities: Mapping[str, float] = field(default_factory=dict)


class AbstentionPolicy(str, Enum):
    Allowed = "allowed"
    Forbidden = "forbidden"


@dataclass(frozen=True)
class DecisionProfile:
    """Versioned schema and calibration boundary for typed decisions.

    Confidence has no portable meaning outside this profile. Thresholds, if
    introduced later, belong in ``calibration_metadata`` for this exact
    schema/version rather than in a global provider rule.
    """

    id: str
    version: str
    choices: tuple[str, ...]
    calibration_metadata: Mapping[str, Any] = field(default_factory=dict)
    abstention_policy: AbstentionPolicy = AbstentionPolicy.Allowed

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Decision profile id must not be empty.")
        if not self.version:
            raise ValueError("Decision profile version must not be empty.")
        if not self.choices:
            raise ValueError("Decision profile must define at least one choice.")
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("Decision profile choices must be unique.")

    def request(
        self,
        question: str,
        *,
        state: Mapping[str, Any] | None = None,
    ) -> TypedDecisionRequest:
        return TypedDecisionRequest(
            profile=self.id,
            profile_version=self.version,
            question=question,
            choices=self.choices,
            state=state or {},
        )

    def validate(self, decision: TypedDecision) -> None:
        if decision.abstained and decision.choice is not None:
            raise ValueError("An abstained decision cannot contain a choice.")
        if not decision.abstained and decision.choice is None:
            raise ValueError("A non-abstained decision must contain a choice.")
        if decision.profile_id != self.id:
            raise ValueError(
                f"Decision profile mismatch: expected {self.id!r}, got {decision.profile_id!r}."
            )
        if decision.profile_version != self.version:
            raise ValueError(
                "Decision profile version mismatch: "
                f"expected {self.version!r}, got {decision.profile_version!r}."
            )
        if decision.abstained:
            if self.abstention_policy is AbstentionPolicy.Forbidden:
                raise ValueError(f"Profile {self.id!r} does not allow abstention.")
            return
        if decision.choice not in self.choices:
            raise ValueError(
                f"Choice {decision.choice!r} is not valid for profile {self.id!r} v{self.version}."
            )


class TypedDecisionProvider(Protocol):
    """A bounded decision service; it does not define Onto4 semantics."""

    def decide(self, request: TypedDecisionRequest) -> TypedDecision:
        ...


class TypedDecisionBatchProvider(Protocol):
    """Optional fan-out capability over one shared request state.

    Implementations must reject a batch whose requests do not share state and
    profile/schema identity.
    """

    def decide_many(
        self, requests: Sequence[TypedDecisionRequest]
    ) -> Sequence[TypedDecision]:
        ...


@dataclass(frozen=True)
class InterpretationRequest:
    """Input accepted by an interpretation provider."""

    source_text: str
    conceptual_depth: ConceptualDepth | None = None
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
    """Produce candidates; assessment remains a separate deterministic step.

    A returned candidate's ``reading_id``, when present, must refer to a
    reading in ``request.interpretation``. Candidate assumptions must either
    trace to that interpretation's presuppositions or be explicitly marked as
    assumptions introduced during formalization. The current string-only
    assumption shape makes that provenance normative rather than machine-
    validated.
    """

    def formalize(self, request: FormalizationRequest) -> Sequence[FormalizationCandidate]:
        ...
