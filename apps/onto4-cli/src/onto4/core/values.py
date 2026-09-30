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


class AssessmentState(str, Enum):
    Assessed = "Assessed"
    FormalizationUnresolved = "FormalizationUnresolved"
    InvalidRequest = "InvalidRequest"


class UnknownReason(str, Enum):
    InsufficientEvidence = "insufficient_evidence"
    ConflictingEvidence = "conflicting_evidence"
    UndeterminedCompound = "undetermined_compound"
    TruthNotEstablished = "truth_not_established"
    FormalizationUnresolved = "formalization_unresolved"
