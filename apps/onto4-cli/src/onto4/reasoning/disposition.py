"""Deterministic workflow dispositions, separate from Onto4 verdicts."""

from enum import Enum


class PipelineDisposition(str, Enum):
    Complete = "Complete"
    AskClarification = "AskClarification"
    NeedEvidence = "NeedEvidence"
    CannotProceed = "CannotProceed"
