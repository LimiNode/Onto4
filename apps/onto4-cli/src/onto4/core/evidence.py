"""Evidence is kept separate from the Onto4 semantic verdict."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ast import Expr, expression_key
from .values import Evidence4, Verdict


def parse_evidence(value: object) -> Evidence4:
    if isinstance(value, Evidence4):
        return value
    if isinstance(value, bool):
        return Evidence4.TrueOnly if value else Evidence4.FalseOnly
    normalized = str(value).strip().lower().replace("_", "")
    aliases = {
        "neither": Evidence4.Neither,
        "true": Evidence4.TrueOnly,
        "trueonly": Evidence4.TrueOnly,
        "false": Evidence4.FalseOnly,
        "falseonly": Evidence4.FalseOnly,
        "both": Evidence4.Both,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown evidence value: {value!r}") from exc


def parse_truth(value: object) -> Verdict:
    if isinstance(value, Verdict):
        if value is Verdict.C:
            raise ValueError("C is not an atomic truth result; it comes from admission.")
        return value
    normalized = str(value).strip().upper()
    if normalized not in {"T", "F", "U"}:
        raise ValueError(f"Unknown atomic truth value: {value!r}")
    return Verdict(normalized)


@dataclass
class EvidenceStore:
    entries: dict[str, Evidence4] = field(default_factory=dict)

    def for_expression(self, expr: Expr) -> Evidence4 | None:
        return self.entries.get(expression_key(expr))

    def for_key(self, key: str) -> Evidence4 | None:
        return self.entries.get(key)


@dataclass
class TruthStore:
    """Established atomic results, kept separate from supporting evidence."""

    entries: dict[str, Verdict] = field(default_factory=dict)

    def for_expression(self, expr: Expr) -> Verdict | None:
        return self.entries.get(expression_key(expr))
