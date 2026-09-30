"""Canonical strict Onto4 evaluator."""

from __future__ import annotations

from dataclasses import dataclass, field

from .admission import AdmissionStatus, Diagnostic, admit
from .ast import And, Equivalent, Expr, Implies, Not, Or, PredicateExpr
from .context import AssessmentContext
from .values import AssessmentState, Evidence4, SemanticStatus, UnknownReason, Verdict


class UnsupportedProfile(ValueError):
    """Raised when a caller requests a profile not implemented by this MVP."""


@dataclass(frozen=True)
class AssessmentResult:
    state: AssessmentState
    semantic_status: SemanticStatus | None
    verdict: Verdict | None
    evidence: Evidence4 | None
    unknown_reasons: tuple[UnknownReason, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class AtomicAssessment:
    verdict: Verdict
    evidence: Evidence4
    reasons: tuple[UnknownReason, ...] = ()


@dataclass(frozen=True)
class _Evaluated:
    verdict: Verdict
    evidence: Evidence4 | None
    reasons: tuple[UnknownReason, ...] = field(default_factory=tuple)


def _validate_context(context: AssessmentContext) -> None:
    if context.semantics.name != "strict_onto4" or not context.semantics.strict:
        raise UnsupportedProfile(
            "Only the strict_onto4 semantic profile is implemented in this MVP."
        )
    if context.inference.name != "direct_evidence":
        raise UnsupportedProfile(
            "Only the direct_evidence inference profile is implemented in this MVP."
        )


def _atomic_assessment(node: PredicateExpr, context: AssessmentContext) -> AtomicAssessment:
    evidence = context.evidence.for_expression(node) or Evidence4.Neither
    established = context.verdicts.for_expression(node)
    if established is not None:
        reasons = ()
        if established is Verdict.U:
            reasons = (
                UnknownReason.ConflictingEvidence
                if evidence is Evidence4.Both
                else UnknownReason.TruthNotEstablished,
            )
        return AtomicAssessment(established, evidence, reasons)
    if evidence is Evidence4.Both:
        return AtomicAssessment(Verdict.U, evidence, (UnknownReason.ConflictingEvidence,))
    if evidence is Evidence4.Neither:
        return AtomicAssessment(Verdict.U, evidence, (UnknownReason.InsufficientEvidence,))
    # Supporting evidence alone is not an established truth verdict.
    return AtomicAssessment(Verdict.U, evidence, (UnknownReason.TruthNotEstablished,))


def _strict_binary(left: _Evaluated, right: _Evaluated, operator: str) -> _Evaluated:
    # Canonical strict semantics: C is never hidden by a neighbouring branch.
    if left.verdict is Verdict.C or right.verdict is Verdict.C:
        return _Evaluated(Verdict.C, None)

    if operator == "and":
        if left.verdict is Verdict.F or right.verdict is Verdict.F:
            return _Evaluated(Verdict.F, None)
        if left.verdict is Verdict.T and right.verdict is Verdict.T:
            return _Evaluated(Verdict.T, None)
    elif operator == "or":
        if left.verdict is Verdict.T or right.verdict is Verdict.T:
            return _Evaluated(Verdict.T, None)
        if left.verdict is Verdict.F and right.verdict is Verdict.F:
            return _Evaluated(Verdict.F, None)
    elif operator == "implies":
        if left.verdict is Verdict.F or right.verdict is Verdict.T:
            return _Evaluated(Verdict.T, None)
        if left.verdict is Verdict.T:
            return _Evaluated(right.verdict, None, right.reasons)
        if right.verdict is Verdict.F:
            return _Evaluated(Verdict.U, None, (UnknownReason.UndeterminedCompound,))
    elif operator == "equivalent":
        if left.verdict is Verdict.U or right.verdict is Verdict.U:
            return _Evaluated(Verdict.U, None, (UnknownReason.UndeterminedCompound,))
        return _Evaluated(
            Verdict.T if left.verdict is right.verdict else Verdict.F,
            None,
        )
    return _Evaluated(Verdict.U, None, (UnknownReason.UndeterminedCompound,))


def evaluate(expr: Expr | None, context: AssessmentContext) -> AssessmentResult:
    """Evaluate an admitted expression in a supported assessment context.

    ``None`` represents a missing or unresolved formalization. It deliberately
    yields no Onto4 verdict instead of being collapsed into ``U``.
    """

    _validate_context(context)
    if expr is None:
        return AssessmentResult(
            state=AssessmentState.FormalizationUnresolved,
            semantic_status=None,
            verdict=None,
            evidence=None,
            unknown_reasons=(UnknownReason.FormalizationUnresolved,),
            diagnostics=(Diagnostic("formalization_unresolved", "No admitted formalization was supplied."),),
        )

    admission = admit(expr, context)
    if admission.status is AdmissionStatus.CategoryError:
        return AssessmentResult(
            state=AssessmentState.Assessed,
            semantic_status=SemanticStatus.Inapplicable,
            verdict=Verdict.C,
            evidence=None,
            diagnostics=admission.diagnostics,
        )
    if admission.status is AdmissionStatus.Unresolved:
        return AssessmentResult(
            state=AssessmentState.FormalizationUnresolved,
            semantic_status=None,
            verdict=None,
            evidence=None,
            unknown_reasons=(UnknownReason.FormalizationUnresolved,),
            diagnostics=admission.diagnostics,
        )
    if admission.status is AdmissionStatus.InvalidRequest:
        return AssessmentResult(
            state=AssessmentState.InvalidRequest,
            semantic_status=None,
            verdict=None,
            evidence=None,
            diagnostics=admission.diagnostics,
        )

    def visit(node: Expr) -> _Evaluated:
        if isinstance(node, PredicateExpr):
            result = _atomic_assessment(node, context)
            return _Evaluated(result.verdict, result.evidence, result.reasons)
        if isinstance(node, Not):
            result = visit(node.operand)
            if result.verdict is Verdict.C:
                return result
            mapping = {Verdict.T: Verdict.F, Verdict.F: Verdict.T, Verdict.U: Verdict.U}
            direct_evidence = context.evidence.for_expression(node)
            return _Evaluated(mapping[result.verdict], direct_evidence, result.reasons)
        if isinstance(node, And):
            result = _strict_binary(visit(node.left), visit(node.right), "and")
        elif isinstance(node, Or):
            result = _strict_binary(visit(node.left), visit(node.right), "or")
        elif isinstance(node, Implies):
            result = _strict_binary(visit(node.left), visit(node.right), "implies")
        elif isinstance(node, Equivalent):
            result = _strict_binary(visit(node.left), visit(node.right), "equivalent")
        else:
            raise TypeError(f"Unsupported expression: {type(node)!r}")
        # A compound evidence projection is either explicitly supplied for the
        # whole expression or remains uncomputed (None), never falsely Neither.
        return _Evaluated(result.verdict, context.evidence.for_expression(node), result.reasons)

    result = visit(expr)
    return AssessmentResult(
        state=AssessmentState.Assessed,
        semantic_status=SemanticStatus.Admitted,
        verdict=result.verdict,
        evidence=result.evidence,
        unknown_reasons=result.reasons,
    )
