"""Opt-in provider-stage diagnostics without exposing model responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProviderStageEvent:
    """One safe lifecycle event emitted by a model-backed provider."""

    stage: str
    phase: str
    elapsed_seconds: float
    detail: str = ""


ProviderTrace = Callable[[ProviderStageEvent], None]


def emit_provider_trace(trace: ProviderTrace | None, event: ProviderStageEvent) -> None:
    """Send diagnostics without allowing a trace sink to affect provider behavior."""

    if trace is None:
        return
    try:
        trace(event)
    except Exception:
        # Diagnostics are deliberately observational and fail open.
        return


__all__ = ["ProviderStageEvent", "ProviderTrace", "emit_provider_trace"]
