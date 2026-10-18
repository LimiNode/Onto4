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
    project_assessment_context,
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
    return assess_interpretation(
        interpretation,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=clarification_policy,
    )


def assess_interpretation(
    interpretation: InterpretationSpace,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> AskResult:
    """Run one explicit formalization and assessment pass for a snapshot."""

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
    disposition, reason = determine_disposition(context)
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


def ask_per_reading(
    request: InterpretationRequest,
    *,
    interpretation_provider: InterpretationProvider,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> AskResult:
    """Interpret once, then use host-bound reading/context formalization."""

    interpretation = interpretation_provider.interpret(request)
    return assess_interpretation_per_reading(
        interpretation,
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=clarification_policy,
    )


def formalize_per_reading_and_context(
    interpretation: InterpretationSpace,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
) -> tuple[FormalizationCandidate, ...]:
    """Fan out host-bound formalization requests for one reading/context pair.

    The provider receives exact immutable reading and context identity.  It may
    propose expression content, but the orchestration boundary rejects any
    returned candidate whose provenance does not match the request.
    """

    candidates: list[FormalizationCandidate] = []
    if not interpretation.readings:
        return tuple(formalization_provider.formalize(FormalizationRequest(interpretation)))
    for reading in interpretation.readings:
        for context_id in contexts:
            returned = tuple(
                formalization_provider.formalize(
                    FormalizationRequest(
                        interpretation,
                        reading=reading,
                        context_id=context_id,
                        context_projection=project_assessment_context(
                            context_id, contexts[context_id]
                        ),
                    )
                )
            )
            if len(returned) != 1:
                raise ValueError(
                    "Per-reading formalization must return exactly one candidate "
                    f"for reading {reading.id!r} and context {context_id!r}."
                )
            candidate = returned[0]
            if candidate.reading_id != reading.id:
                raise ValueError(
                    "Formalization candidate reading provenance does not match the request."
                )
            if candidate.context_id != context_id:
                raise ValueError(
                    "Formalization candidate context provenance does not match the request."
                )
            candidates.append(candidate)
    candidate_ids = [candidate.id for candidate in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Per-reading formalization returned duplicate candidate identities.")
    return tuple(candidates)


def assess_interpretation_per_reading(
    interpretation: InterpretationSpace,
    *,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: ClarificationPolicy,
) -> AskResult:
    """Assess a snapshot after deterministic reading/context fan-out."""

    candidates = formalize_per_reading_and_context(
        interpretation,
        formalization_provider=formalization_provider,
        contexts=contexts,
    )
    assessments = assess_candidates(candidates, contexts)
    landscape = aggregate_assessments(assessments)
    context = ClarificationContext(
        interpretation=interpretation,
        candidates=candidates,
        assessments=assessments,
        landscape=landscape,
    )
    disposition, reason = determine_disposition(context)
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


def determine_disposition(context: ClarificationContext) -> tuple[PipelineDisposition, str]:
    landscape = context.landscape
    if landscape.status is CrossCandidateStatus.InvalidRequest:
        return PipelineDisposition.CannotProceed, "invalid_request"
    if material_ambiguity(context):
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


def material_ambiguity(context: ClarificationContext) -> bool:
    """Return whether an interpretation ambiguity changes this assessment.

    An ambiguity is not material merely because a provider listed it.  The
    host may suppress it only when distinct readings have exactly the same
    formal expression and assumptions in one assessed context.  Equal
    ``T/F/U/C`` values alone are never enough: they can arise from different
    meanings, missing evidence, or independent category errors.  With one
    reading, repeated candidates, unresolved candidates, or a reflective/
    philosophical depth we retain conservative clarification behaviour.
    """

    if not context.interpretation.ambiguities:
        return False
    if context.landscape.status is not CrossCandidateStatus.StableAcrossCandidates:
        return True
    interpretation = context.interpretation
    if interpretation.conceptual_depth.value not in {"ordinary", "reflective"}:
        return True

    by_reading: dict[str, list[object]] = {}
    for item in context.assessments:
        reading_id = item.candidate.reading_id
        if reading_id is None:
            return True
        by_reading.setdefault(reading_id, []).append(item)
    if len(by_reading) < 2 or any(len(items) != 1 for items in by_reading.values()):
        return True

    footprints = [
        (items[0].candidate.formalization, items[0].candidate.assumptions)
        for items in by_reading.values()
    ]
    baseline = footprints[0]
    return any(footprint != baseline for footprint in footprints[1:])
