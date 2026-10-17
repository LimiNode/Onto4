"""Model-backed corpus execution using the existing Onto4 orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from onto4.core import AssessmentContext
from .ask import ask_per_reading
from onto4.providers import (
    FormalizationProvider,
    InterpretationProvider,
    InterpretationRequest,
    ProviderSchemaError,
    ProviderTransportError,
)
from onto4.providers.diagnostics import ProviderStageEvent, ProviderTrace
from onto4.reasoning import FixtureClarificationPolicy, PipelineDisposition

from .clarification_corpus import ClarificationCorpusCase
from .evaluation import CaseExecution, EvaluationOutcome
from .interactive import ModelClarificationPolicy, run_interactive_dialogue


@dataclass
class ModelCaseExecutor:
    """Run one corpus case through the real provider/orchestration boundary.

    The executor records only safe stage metadata. It never puts source text,
    hidden oracle fields or model payloads in a ``CaseExecution`` receipt.
    """

    interpretation_provider: InterpretationProvider
    formalization_provider: FormalizationProvider
    contexts: Mapping[str, AssessmentContext]
    max_turns: int = 4
    trace_sink: ProviderTrace | None = None
    _last_events: list[ProviderStageEvent] = field(default_factory=list, init=False)

    def _trace(self, event: ProviderStageEvent) -> None:
        self._last_events.append(event)
        if self.trace_sink is not None:
            self.trace_sink(event)

    def _metadata(self) -> tuple[int, dict[str, float], dict[str, str]]:
        timings: dict[str, float] = {}
        outcomes: dict[str, str] = {}
        calls = 0
        for event in self._last_events:
            if event.phase == "started":
                calls += 1
            if event.elapsed_seconds:
                # A stage emits several observational events; the final event
                # carries the full elapsed duration, so do not double-count
                # intermediate response/json markers.
                timings[event.stage] = max(
                    timings.get(event.stage, 0.0), event.elapsed_seconds
                )
            outcomes[event.stage] = event.phase
        return calls, timings, outcomes

    def _request(self, case: ClarificationCorpusCase) -> InterpretationRequest:
        state = {
            "evaluation_case_id": case.case_id,
            "model_input": case.model_input,
        }
        if case.model_input == "contextual" and case.context is not None:
            state["context_id"] = case.context
        return InterpretationRequest(case.utterance, state=state)

    def __call__(
        self,
        case: ClarificationCorpusCase,
        *,
        request_timeout_seconds: float,
    ) -> CaseExecution:
        del request_timeout_seconds  # transport profile owns the actual timeout
        self._last_events = []
        try:
            request = self._request(case)
            if case.mode == "dialogue" and case.dialogue:
                answers = [
                    turn["text"]
                    for turn in case.dialogue
                    if turn.get("role") == "user"
                ][1:]
                answer_index = 0

                def input_fn(_: str) -> str:
                    nonlocal answer_index
                    if answer_index >= len(answers):
                        return "none_of_the_above"
                    answer = answers[answer_index]
                    answer_index += 1
                    return answer

                policy = ModelClarificationPolicy(
                    FixtureClarificationPolicy(),
                    self.interpretation_provider,
                )
                result = run_interactive_dialogue(
                    request,
                    interpretation_provider=self.interpretation_provider,
                    refinement_provider=self.interpretation_provider,
                    formalization_provider=self.formalization_provider,
                    contexts=self.contexts,
                    clarification_policy=policy,
                    input_fn=input_fn,
                    output_fn=lambda _: None,
                    max_turns=self.max_turns,
                )
                outcome = {
                    "complete": EvaluationOutcome.ASSESSMENT_COMPLETED,
                    "need_evidence": EvaluationOutcome.FORMALIZATION_UNRESOLVED,
                    "cannot_proceed": EvaluationOutcome.FORMALIZATION_UNRESOLVED,
                    "max_turns_reached": EvaluationOutcome.CLARIFICATION_REQUESTED,
                    "no_new_admissible_question": EvaluationOutcome.CLARIFICATION_REQUESTED,
                }.get(result.stop_reason, EvaluationOutcome.CLARIFICATION_REQUESTED)
                ask_result = (
                    result.session.assessment.ask_result
                    if result.session.assessment is not None
                    else None
                )
            else:
                policy = FixtureClarificationPolicy()
                ask_result = ask_per_reading(
                    request,
                    interpretation_provider=self.interpretation_provider,
                    formalization_provider=self.formalization_provider,
                    contexts=self.contexts,
                    clarification_policy=policy,
                )
                outcome = {
                    PipelineDisposition.Complete: EvaluationOutcome.ASSESSMENT_COMPLETED,
                    PipelineDisposition.AskClarification: EvaluationOutcome.CLARIFICATION_REQUESTED,
                    PipelineDisposition.NeedEvidence: EvaluationOutcome.FORMALIZATION_UNRESOLVED,
                    PipelineDisposition.CannotProceed: EvaluationOutcome.FORMALIZATION_UNRESOLVED,
                }[ask_result.disposition]
            calls, timings, outcomes = self._metadata()
            verdict = None
            if ask_result is not None and len(ask_result.assessments) == 1:
                verdict = (
                    ask_result.assessments[0].result.verdict.value
                    if ask_result.assessments[0].result.verdict is not None
                    else None
                )
            return CaseExecution(
                outcome,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                semantic_verdict=verdict,
                detail_code="model_backed",
            )
        except ProviderTransportError as exc:
            calls, timings, outcomes = self._metadata()
            return CaseExecution(
                EvaluationOutcome.TRANSPORT_ERROR,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                detail_code=type(exc).__name__,
            )

        except ProviderSchemaError as exc:
            calls, timings, outcomes = self._metadata()
            return CaseExecution(
                EvaluationOutcome.SCHEMA_INVALID,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                detail_code=type(exc).__name__,
            )
        except (KeyError, ValueError) as exc:
            calls, timings, outcomes = self._metadata()
            return CaseExecution(
                EvaluationOutcome.PROVENANCE_INVALID,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                detail_code=type(exc).__name__,
            )

    def provider_trace(self, event: ProviderStageEvent) -> None:
        """Collect one adapter event for the current case and forward it safely."""

        self._trace(event)


__all__ = ["ModelCaseExecutor"]
