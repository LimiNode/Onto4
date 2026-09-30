"""Canonical strict Onto4 evaluator."""

from __future__ import annotations

from dataclasses import dataclass, field

from .admission import Diagnostic, admit
from .ast import And, Equivalent, Expr, Implies, Not, Or, PredicateExpr
from .context import AssessmentContext
from .values import Evidence4, SemanticStatus, UnknownReason, Verdict


@dataclass(frozen=True)
class AssessmentResult:
    semantic_status: SemanticStatus
    verdict: Verdict | None
    evidence: Evidence4
    unknown_reasons: tuple[UnknownReason, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class _Evaluated:
    verdict: Verdict
    evidence: Evidence4
    reasons: tuple[UnknownReason, ...] = field(default_factory=tuple)


def _atom_verdict(evidence: Evidence4) -> tuple[Verdict, tuple[UnknownReason, ...]]:
    if evidence is Evidence4.TrueOnly:
        return Verdict.T, ()
    if evidence is Evidence4.FalseOnly:
        return Verdict.F, ()
    if evidence is Evidence4.Both:
        return Verdict.U, (UnknownReason.ConflictingEvidence,)
    return Verdict.U, (UnknownReason.InsufficientEvidence,)


def _strict_binary(left: _Evaluated, right: _Evaluated, operator: str) -> _Evaluated:
    # Canonical strict semantics: C is never hidden by a neighbouring branch.
    if left.verdict is Verdict.C or right.verdict is Verdict.C:
        return _Evaluated(Verdict.C, Evidence4.Neither)

    if operator == "and":
        if left.verdict is Verdict.F or right.verdict is Verdict.F:
            return _Evaluated(Verdict.F, Evidence4.Neither)
        if left.verdict is Verdict.T and right.verdict is Verdict.T:
            return _Evaluated(Verdict.T, Evidence4.Neither)
    elif operator == "or":
        if left.verdict is Verdict.T or right.verdict is Verdict.T:
            return _Evaluated(Verdict.T, Evidence4.Neither)
        if left.verdict is Verdict.F and right.verdict is Verdict.F:
            return _Evaluated(Verdict.F, Evidence4.Neither)
    elif operator == "implies":
        if left.verdict is Verdict.F or right.verdict is Verdict.T:
            return _Evaluated(Verdict.T, Evidence4.Neither)
        if left.verdict is Verdict.T:
            return _Evaluated(right.verdict, Evidence4.Neither, right.reasons)
        if right.verdict is Verdict.F:
            return _Evaluated(Verdict.U, Evidence4.Neither, (UnknownReason.UndeterminedCompound,))
    elif operator == "equivalent":
        if left.verdict is Verdict.U or right.verdict is Verdict.U:
            return _Evaluated(Verdict.U, Evidence4.Neither, (UnknownReason.UndeterminedCompound,))
        return _Evaluated(
            Verdict.T if left.verdict is right.verdict else Verdict.F,
            Evidence4.Neither,
        )
    return _Evaluated(Verdict.U, Evidence4.Neither, (UnknownReason.UndeterminedCompound,))


def evaluate(expr: Expr | None, context: AssessmentContext) -> AssessmentResult:
    """Evaluate an admitted expression in a context.

    ``None`` represents a missing or unresolved formalization. It deliberately
    yields no Onto4 verdict instead of being collapsed into ``U``.
    """

    if expr is None:
        return AssessmentResult(
            semantic_status=SemanticStatus.Unresolved,
            verdict=None,
            evidence=Evidence4.Neither,
            unknown_reasons=(UnknownReason.FormalizationUnresolved,),
            diagnostics=(Diagnostic("formalization_unresolved", "No admitted formalization was supplied."),),
        )

    admission = admit(expr, context)
    if not admission.admitted:
        return AssessmentResult(
            semantic_status=SemanticStatus.Inapplicable,
            verdict=Verdict.C,
            evidence=Evidence4.Neither,
            diagnostics=admission.diagnostics,
        )

    def visit(node: Expr) -> _Evaluated:
        if isinstance(node, PredicateExpr):
            evidence = context.evidence.for_expression(node)
            verdict, reasons = _atom_verdict(evidence)
            return _Evaluated(verdict, evidence, reasons)
        if isinstance(node, Not):
            result = visit(node.operand)
            if result.verdict is Verdict.C:
                return result
            mapping = {Verdict.T: Verdict.F, Verdict.F: Verdict.T, Verdict.U: Verdict.U}
            evidence_mapping = {
                Evidence4.TrueOnly: Evidence4.FalseOnly,
                Evidence4.FalseOnly: Evidence4.TrueOnly,
                Evidence4.Neither: Evidence4.Neither,
                Evidence4.Both: Evidence4.Both,
            }
            return _Evaluated(mapping[result.verdict], evidence_mapping[result.evidence], result.reasons)
        if isinstance(node, And):
            return _strict_binary(visit(node.left), visit(node.right), "and")
        if isinstance(node, Or):
            return _strict_binary(visit(node.left), visit(node.right), "or")
        if isinstance(node, Implies):
            return _strict_binary(visit(node.left), visit(node.right), "implies")
        if isinstance(node, Equivalent):
            return _strict_binary(visit(node.left), visit(node.right), "equivalent")
        raise TypeError(f"Unsupported expression: {type(node)!r}")

    result = visit(expr)
    return AssessmentResult(
        semantic_status=SemanticStatus.Admitted,
        verdict=result.verdict,
        evidence=result.evidence,
        unknown_reasons=result.reasons,
    )
