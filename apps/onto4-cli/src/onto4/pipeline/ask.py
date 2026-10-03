"""One deterministic interpretation/formalization/assessment pass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from onto4.core import AssessmentContext, AssessmentState, Verdict
from onto4.core.values import UnknownReason
from onto4.providers import (
    FormalizationProvider,
    FormalizationRequest,
    InterpretationProvider,
    InterpretationRequest,
)
from onto4.reasoning import (
    AssessmentLandscape,
    CandidateAssessment,
    ClarificationContext,
    ClarificationPolicy,
    ClarificationQuestion,
    CrossCandidateStatus,
    FormalizationCandidate,
    InterpretationSpace,
    PipelineDisposition,
    assess_candidates,
    aggregate_assessments,
)


@dataclass(frozen=True)
class AskResult:
    interpretation: InterpretationSpace
    candidates: tuple[FormalizationCandidate, ...]
    assessments: tuple[CandidateAssessment, ...]
    landscape: AssessmentLandscape
    disposition: PipelineDisposition
    clarification_question: ClarificationQuestion | None = None
    reason: str = ""


def ask(
    request: InterpretationRequest,
    *,
    interpretation_provider: InterpretationProvider,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> AskResult:
    interpretation = interpretation_provider.interpret(request)
    candidates = tuple(
        formalization_provider.formalize(FormalizationRequest(interpretation))
    )
    assessments = assess_candidates(candidates, contexts)
    landscape = aggregate_assessments(assessments)
    context = ClarificationContext(
        interpretation=interpretation,
        candidates=candidates,
        assessments=assessments,
        landscape=landscape,
    )
    disposition, reason = _disposition(context)
    question = (
        clarification_policy.choose(context)
        if disposition is PipelineDisposition.AskClarification
        else None
    )
    return AskResult(
        interpretation=interpretation,
        candidates=candidates,
        assessments=assessments,
        landscape=landscape,
        disposition=disposition,
        clarification_question=question,
        reason=reason,
    )


def _disposition(context: ClarificationContext) -> tuple[PipelineDisposition, str]:
    landscape = context.landscape
    if landscape.status is CrossCandidateStatus.InvalidRequest:
        return PipelineDisposition.CannotProceed, "invalid_request"
    if context.interpretation.ambiguities:
        return PipelineDisposition.AskClarification, "material_ambiguity"
    if landscape.status is CrossCandidateStatus.FormalizationUnresolved:
        return PipelineDisposition.AskClarification, "formalization_unresolved"
    if landscape.status in {
        CrossCandidateStatus.ContextDependent,
        CrossCandidateStatus.FormalizationConflict,
        CrossCandidateStatus.MixedDependence,
    }:
        return PipelineDisposition.AskClarification, landscape.status.value
    if any(
        item.result.state is AssessmentState.Assessed
        and item.result.verdict is Verdict.U
        and bool(item.result.unknown_reasons)
        and any(
            reason
            in {
                UnknownReason.InsufficientEvidence,
                UnknownReason.ConflictingEvidence,
                UnknownReason.TruthNotEstablished,
                UnknownReason.UndeterminedCompound,
            }
            for reason in item.result.unknown_reasons
        )
        for item in context.assessments
    ):
        return PipelineDisposition.NeedEvidence, "insufficient_or_conflicting_evidence"
    return PipelineDisposition.Complete, "assessed"
