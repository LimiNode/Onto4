"""A deliberately small typed expression tree for the first Onto4 slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Term:
    name: str
    declared_type: str | None = None


@dataclass(frozen=True)
class PredicateCall:
    name: str
    args: tuple[Term, ...] = ()

    def key(self) -> str:
        return f"{self.name}({', '.join(term.name for term in self.args)})"


@dataclass(frozen=True)
class PredicateExpr:
    call: PredicateCall


@dataclass(frozen=True)
class Not:
    operand: "Expr"


@dataclass(frozen=True)
class And:
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class Or:
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class Implies:
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class Equivalent:
    left: "Expr"
    right: "Expr"


Expr = Union[PredicateExpr, Not, And, Or, Implies, Equivalent]


def expression_key(expr: Expr) -> str:
    """Return a stable, human-readable key for evidence lookup."""

    if isinstance(expr, PredicateExpr):
        return expr.call.key()
    if isinstance(expr, Not):
        return f"not({expression_key(expr.operand)})"
    if isinstance(expr, And):
        return f"and({expression_key(expr.left)}, {expression_key(expr.right)})"
    if isinstance(expr, Or):
        return f"or({expression_key(expr.left)}, {expression_key(expr.right)})"
    if isinstance(expr, Implies):
        return f"implies({expression_key(expr.left)}, {expression_key(expr.right)})"
    if isinstance(expr, Equivalent):
        return f"equivalent({expression_key(expr.left)}, {expression_key(expr.right)})"
    raise TypeError(f"Unsupported expression: {type(expr)!r}")
