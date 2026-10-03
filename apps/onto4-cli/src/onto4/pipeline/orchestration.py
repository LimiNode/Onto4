"""Named entry point for the deterministic orchestration pass."""

from .ask import AskResult, ask


def orchestrate_once(*args, **kwargs) -> AskResult:
    """Run one interpretation → formalization → assessment pass."""

    return ask(*args, **kwargs)


__all__ = ["AskResult", "orchestrate_once"]
