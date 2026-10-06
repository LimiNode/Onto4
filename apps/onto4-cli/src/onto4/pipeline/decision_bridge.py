"""Bridge typed workflow decisions into deterministic clarification policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from onto4.providers import (
    DecisionProfile,
    DeterministicDecisionPolicy,
    TypedDecision,
    TypedDecisionProvider,
    TypedDecisionRequest,
)
from onto4.reasoning import (
    ClarificationContext,
    ClarificationKind,
    ClarificationQuestion,
    CrossCandidateStatus,
    KindAwareClarificationPolicy,
    PipelineDisposition,
)

from .ask import determine_disposition

CLARIFICATION_REFINEMENT_CHOICES = (
    "NeedMeaningClarification",
    "NeedOntologyClarification",
    "NeedReferenceClarification",
    "NeedContextClarification",
    "NeedPresuppositionClarification",
    "NeedFormalizationClarification",
)
EVIDENCE_REFINEMENT_CHOICES = ("SelectEvidencePath",)
COMPLETE_REFINEMENT_CHOICES = ("PresentResult",)
FAILURE_REFINEMENT_CHOICES = ("ReportFailure",)
CLARIFICATION_KIND_BY_REFINEMENT = {
    "NeedMeaningClarification": ClarificationKind.Meaning,
    "NeedOntologyClarification": ClarificationKind.Ontology,
    "NeedReferenceClarification": ClarificationKind.Reference,
    "NeedContextClarification": ClarificationKind.Context,
    "NeedPresuppositionClarification": ClarificationKind.Presupposition,
    "NeedFormalizationClarification": ClarificationKind.Formalization,
}


@dataclass(frozen=True)
class ClarificationDecisionResult:
    request: TypedDecisionRequest
    decision: TypedDecision
    selected_choice: str | None
    admissible_disposition: PipelineDisposition
    disposition: PipelineDisposition | None


@dataclass(frozen=True)
class ClarificationQuestionDecision:
    """A bounded decision resolved to one deterministic clarification question."""

    decision_result: ClarificationDecisionResult
    question: ClarificationQuestion | None


def _clarification_refinement_choices(
    context: ClarificationContext,
) -> tuple[str, ...]:
    interpretation = context.interpretation
    landscape = context.landscape
    if interpretation.ambiguities:
        return ("NeedMeaningClarification",)
    if landscape.status is CrossCandidateStatus.FormalizationConflict:
        has_reading_provenance = bool(context.assessments) and all(
            item.candidate.reading_id is not None for item in context.assessments
        )
        if has_reading_provenance:
            return ("NeedMeaningClarification",)
        return ("NeedFormalizationClarification",)
    if landscape.status is CrossCandidateStatus.ContextDependent:
        return ("NeedContextClarification",)
    if landscape.status is CrossCandidateStatus.MixedDependence:
        has_reading_provenance = bool(context.assessments) and all(
            item.candidate.reading_id is not None for item in context.assessments
        )
        if has_reading_provenance:
            return ("NeedMeaningClarification",)
        return ("NeedFormalizationClarification",)
    if landscape.status is CrossCandidateStatus.FormalizationUnresolved:
        diagnostic_codes = {
            diagnostic.code
            for item in context.assessments
            if item.candidate.id in landscape.unresolved_candidate_ids
            for diagnostic in item.result.diagnostics
        }
        diagnostic_refinements = (
            ("unknown_symbol", "NeedReferenceClarification"),
            ("unknown_predicate", "NeedMeaningClarification"),
            ("ontology_unresolved", "NeedOntologyClarification"),
            ("presupposition_unresolved", "NeedPresuppositionClarification"),
        )
        refinements = tuple(
            refinement
            for code, refinement in diagnostic_refinements
            if code in diagnostic_codes
        )
        return refinements or ("NeedFormalizationClarification",)
    raise ValueError(
        "AskClarification has no provenance-bound refinement source for "
        f"landscape {landscape.status.value!r}."
    )


def _refinement_choices(
    context: ClarificationContext,
    disposition: PipelineDisposition,
) -> tuple[str, ...]:
    if disposition is PipelineDisposition.AskClarification:
        return _clarification_refinement_choices(context)
    if disposition is PipelineDisposition.NeedEvidence:
        return EVIDENCE_REFINEMENT_CHOICES
    if disposition is PipelineDisposition.Complete:
        return COMPLETE_REFINEMENT_CHOICES
    return FAILURE_REFINEMENT_CHOICES


def build_clarification_request(
    context: ClarificationContext,
    profile: DecisionProfile,
) -> TypedDecisionRequest:
    """Encode meta-level clarification state as a bounded typed request."""

    admissible_disposition, _ = determine_disposition(context)
    state: Mapping[str, object] = {
        "interpretation_id": context.interpretation.id,
        "candidate_ids": tuple(candidate.id for candidate in context.candidates),
        "ambiguity_ids": tuple(item.id for item in context.interpretation.ambiguities),
        "reading_ids": tuple(item.id for item in context.interpretation.readings),
        "unresolved_candidate_ids": context.landscape.unresolved_candidate_ids,
        "diagnostic_codes": tuple(
            (item.candidate.id, diagnostic.code)
            for item in context.assessments
            for diagnostic in item.result.diagnostics
        ),
        "landscape_status": context.landscape.status.value,
        "varies_by_context": context.landscape.varies_by_context,
        "varies_by_formalization": context.landscape.varies_by_formalization,
        "admissible_disposition": admissible_disposition.value,
    }
    return profile.request(
        (
            "Choose the next workflow action for interpretation "
            f"{context.interpretation.id!r} with landscape "
            f"{context.landscape.status.value!r}."
        ),
        state=state,
        choices=_refinement_choices(context, admissible_disposition),
    )


def decide_clarification(
    context: ClarificationContext,
    *,
    profile: DecisionProfile,
    provider: TypedDecisionProvider,
) -> ClarificationDecisionResult:
    """Let a bounded provider refine a deterministic branch, never override it."""

    request = build_clarification_request(context, profile)
    admissible_disposition, _ = determine_disposition(context)
    decision = provider.decide(request)
    selected_choice = DeterministicDecisionPolicy(profile).select(decision)
    if selected_choice is None:
        return ClarificationDecisionResult(
            request=request,
            decision=decision,
            selected_choice=None,
            admissible_disposition=admissible_disposition,
            disposition=None,
        )
    if selected_choice not in request.choices:
        raise ValueError(
            f"Decision choice {selected_choice!r} is not admissible for "
            f"workflow branch {admissible_disposition.value!r}."
        )
    return ClarificationDecisionResult(
        request=request,
        decision=decision,
        selected_choice=selected_choice,
        admissible_disposition=admissible_disposition,
        disposition=admissible_disposition,
    )


def decide_clarification_question(
    context: ClarificationContext,
    *,
    profile: DecisionProfile,
    provider: TypedDecisionProvider,
    clarification_policy: KindAwareClarificationPolicy,
) -> ClarificationQuestionDecision:
    """Resolve a bounded refinement to a provenance-aware question.

    Abstention remains explicit and produces no question. Non-clarification
    workflow branches also produce no question. The provider selects only a
    question kind; the deterministic policy owns its wording and targets.
    """

    decision_result = decide_clarification(
        context,
        profile=profile,
        provider=provider,
    )
    if (
        decision_result.disposition is not PipelineDisposition.AskClarification
        or decision_result.selected_choice is None
    ):
        return ClarificationQuestionDecision(decision_result, None)

    try:
        kind = CLARIFICATION_KIND_BY_REFINEMENT[decision_result.selected_choice]
    except KeyError as exc:
        raise ValueError(
            "Selected workflow refinement does not identify a clarification kind: "
            f"{decision_result.selected_choice!r}."
        ) from exc
    question = clarification_policy.choose_for_kind(context, kind)
    if question is None or question.kind is not kind:
        raise ValueError(
            "Clarification policy cannot produce a provenance-aware question "
            f"for selected kind {kind.value!r}."
        )
    return ClarificationQuestionDecision(decision_result, question)
