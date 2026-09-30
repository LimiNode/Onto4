"""Deterministic semantic admission and type checking."""

from __future__ import annotations

from dataclasses import dataclass

from .ast import And, Equivalent, Expr, Implies, Not, Or, PredicateExpr
from .context import AssessmentContext


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    diagnostics: tuple[Diagnostic, ...] = ()


def admit(expr: Expr, context: AssessmentContext) -> AdmissionResult:
    diagnostics: list[Diagnostic] = []

    def visit(node: Expr, path: str) -> None:
        if isinstance(node, PredicateExpr):
            call = node.call
            if call.name in context.ontology.absent_concepts:
                diagnostics.append(
                    Diagnostic(
                        "absent_concept",
                        f"Predicate '{call.name}' is absent from ontology '{context.ontology.name}'.",
                        path,
                    )
                )
                return
            signature = context.ontology.predicates.get(call.name)
            if signature is None:
                diagnostics.append(
                    Diagnostic(
                        "unknown_predicate",
                        f"Predicate '{call.name}' is not defined in ontology '{context.ontology.name}'.",
                        path,
                    )
                )
                return
            if len(call.args) != len(signature.domain):
                diagnostics.append(
                    Diagnostic(
                        "arity_mismatch",
                        f"Predicate '{call.name}' expects {len(signature.domain)} argument(s), got {len(call.args)}.",
                        path,
                    )
                )
                return
            for index, (term, expected_type) in enumerate(zip(call.args, signature.domain)):
                actual_type = context.ontology.types.get(term.name)
                if actual_type is None:
                    diagnostics.append(
                        Diagnostic(
                            "unknown_symbol",
                            f"Symbol '{term.name}' has no type in the ontology.",
                            f"{path}.args[{index}]",
                        )
                    )
                    continue
                if term.declared_type and term.declared_type != actual_type:
                    diagnostics.append(
                        Diagnostic(
                            "declared_type_mismatch",
                            f"Symbol '{term.name}' is declared as '{term.declared_type}' but ontology gives '{actual_type}'.",
                            f"{path}.args[{index}]",
                        )
                    )
                    continue
                if not context.ontology.is_type_compatible(actual_type, expected_type):
                    diagnostics.append(
                        Diagnostic(
                            "type_mismatch",
                            f"Argument '{term.name}' has type '{actual_type}', expected '{expected_type}'.",
                            f"{path}.args[{index}]",
                        )
                    )
            if signature.returns != "Proposition":
                diagnostics.append(
                    Diagnostic(
                        "non_propositional_predicate",
                        f"Predicate '{call.name}' does not return a proposition.",
                        path,
                    )
                )
            return
        if isinstance(node, Not):
            visit(node.operand, f"{path}.operand")
        elif isinstance(node, (And, Or, Implies, Equivalent)):
            visit(node.left, f"{path}.left")
            visit(node.right, f"{path}.right")
        else:
            diagnostics.append(Diagnostic("unsupported_expression", f"Unsupported expression: {type(node)!r}", path))

    visit(expr, "expression")
    return AdmissionResult(not diagnostics, tuple(diagnostics))
