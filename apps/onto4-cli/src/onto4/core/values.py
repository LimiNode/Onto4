"""Small value spaces used by the Onto4 kernel."""

from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    T = "T"
    F = "F"
    U = "U"
    C = "C"


class Evidence4(str, Enum):
    Neither = "Neither"
    TrueOnly = "TrueOnly"
    FalseOnly = "FalseOnly"
    Both = "Both"


class SemanticStatus(str, Enum):
    Admitted = "Admitted"
    Inapplicable = "Inapplicable"
    Unresolved = "Unresolved"


class UnknownReason(str, Enum):
    InsufficientEvidence = "insufficient_evidence"
    ConflictingEvidence = "conflicting_evidence"
    UndeterminedCompound = "undetermined_compound"
    FormalizationUnresolved = "formalization_unresolved"
