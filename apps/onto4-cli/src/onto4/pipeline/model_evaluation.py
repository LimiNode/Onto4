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
from onto4.reasoning import ClarificationKind

from .clarification_corpus import ClarificationCorpusCase
from .evaluation import CaseExecution, EvaluationOutcome
from .interactive import ModelClarificationPolicy, run_interactive_dialogue


class _ReplayError(ValueError):
    """A scripted dialogue cannot be safely replayed against this model turn."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _ReplayPolicy(ModelClarificationPolicy):
    """Validate the first model question against the case's declared intent."""

    expected_kinds: tuple[ClarificationKind | None, ...] = ()
    issued_questions: int = 0

    def questions(self, context):
        questions = super().questions(context)
        if self.issued_questions < len(self.expected_kinds):
            expected_kind = self.expected_kinds[self.issued_questions]
            if expected_kind is not None and not any(
                question.kind is expected_kind for question in questions
            ):
                raise _ReplayError("question_intent_mismatch")
        return questions

    def choose_for_kind(self, context, kind: ClarificationKind):
        question = super().choose_for_kind(context, kind)
        if question is not None:
            object.__setattr__(self, "issued_questions", self.issued_questions + 1)
        return question


class _ContextUnavailable(ValueError):
    pass


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
        occurrences: dict[str, int] = {}
        active_keys: dict[str, str] = {}
        for event in self._last_events:
            if event.phase == "started":
                calls += 1
                occurrences[event.stage] = occurrences.get(event.stage, 0) + 1
                suffix = occurrences[event.stage]
                active_keys[event.stage] = (
                    event.stage if suffix == 1 else f"{event.stage}#{suffix}"
                )
            key = active_keys.get(event.stage, event.stage)
            if event.elapsed_seconds:
                # A stage emits several observational events; the final event
                # carries the full elapsed duration, so do not double-count
                # intermediate response/json markers.
                timings[key] = max(
                    timings.get(key, 0.0), event.elapsed_seconds
                )
            outcomes[key] = event.phase
        return calls, timings, outcomes

    def _request(self, case: ClarificationCorpusCase) -> InterpretationRequest:
        state = {
            "evaluation_case_id": case.case_id,
            "model_input": case.model_input,
        }
        if case.model_input == "contextual" and case.context is not None:
            state["context_id"] = case.context
        return InterpretationRequest(case.utterance, state=state)

    def _case_contexts(self, case: ClarificationCorpusCase) -> Mapping[str, AssessmentContext]:
        if case.context is None:
            return self.contexts
        try:
            return {case.context: self.contexts[case.context]}
        except KeyError as exc:
            raise _ContextUnavailable("context_unavailable") from exc

    @staticmethod
    def _script(
        case: ClarificationCorpusCase,
    ) -> tuple[list[str], int, tuple[ClarificationKind | None, ...]]:
        if not case.dialogue:
            return [], 0, ()
        turns = list(case.dialogue)
        if turns[0].get("role") != "user" or turns[0].get("text") != case.utterance:
            raise _ReplayError("question_intent_mismatch")
        answers: list[str] = []
        assistant_count = 0
        question_kinds: list[ClarificationKind | None] = []
        expected_role = "user"
        for index, turn in enumerate(turns):
            role = turn.get("role")
            if role != expected_role:
                raise _ReplayError("question_intent_mismatch")
            expected_role = "assistant" if role == "user" else "user"
            if role == "assistant":
                assistant_count += 1
                raw_kind = turn.get("question_kind")
                if isinstance(raw_kind, str):
                    try:
                        question_kinds.append(ClarificationKind(raw_kind))
                    except ValueError:
                        raise _ReplayError("question_intent_mismatch") from None
                else:
                    question_kinds.append(None)
            elif index:
                answers.append(str(turn.get("text", "")))
        return answers, assistant_count, tuple(question_kinds)

    @staticmethod
    def _expected_kind(case: ClarificationCorpusCase) -> ClarificationKind | None:
        expected = case.expected_clarification
        if not expected:
            return None
        raw = expected.get("kind")
        if not isinstance(raw, str):
            return None
        try:
            return ClarificationKind(raw)
        except ValueError:
            try:
                return ClarificationKind(raw.capitalize())
            except ValueError:
                return None

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
            case_contexts = self._case_contexts(case)
            if case.mode == "dialogue" and case.dialogue:
                answers, scripted_questions, scripted_kinds = self._script(case)
                expected_kind = self._expected_kind(case)
                expected_kinds = (
                    scripted_kinds
                    if any(kind is not None for kind in scripted_kinds)
                    else ((expected_kind,) if expected_kind else ())
                )
                answer_index = 0

                def input_fn(_: str) -> str:
                    nonlocal answer_index
                    if answer_index >= len(answers):
                        raise _ReplayError("script_exhausted")
                    answer = answers[answer_index]
                    answer_index += 1
                    return answer

                policy = _ReplayPolicy(
                    FixtureClarificationPolicy(),
                    self.interpretation_provider,
                    expected_kinds=expected_kinds,
                )
                result = run_interactive_dialogue(
                    request,
                    interpretation_provider=self.interpretation_provider,
                    refinement_provider=self.interpretation_provider,
                    formalization_provider=self.formalization_provider,
                    contexts=case_contexts,
                    clarification_policy=policy,
                    input_fn=input_fn,
                    output_fn=lambda _: None,
                    max_turns=self.max_turns,
                )
                if (
                    result.stop_reason == "complete"
                    and case.expected_clarification is not None
                    and policy.issued_questions == 0
                ):
                    raise _ReplayError("question_intent_mismatch")
                if policy.issued_questions > scripted_questions:
                    raise _ReplayError("script_exhausted")
                outcome = {
                    "complete": EvaluationOutcome.ASSESSMENT_COMPLETED,
                    "need_evidence": EvaluationOutcome.NEED_EVIDENCE,
                    "cannot_proceed": EvaluationOutcome.CANNOT_PROCEED,
                    "max_turns_reached": EvaluationOutcome.DIALOGUE_INCOMPLETE,
                    "no_new_admissible_question": EvaluationOutcome.DIALOGUE_INCOMPLETE,
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
                    contexts=case_contexts,
                    clarification_policy=policy,
                )
                outcome = {
                    PipelineDisposition.Complete: EvaluationOutcome.ASSESSMENT_COMPLETED,
                    PipelineDisposition.AskClarification: EvaluationOutcome.CLARIFICATION_REQUESTED,
                    PipelineDisposition.NeedEvidence: EvaluationOutcome.NEED_EVIDENCE,
                    PipelineDisposition.CannotProceed: EvaluationOutcome.CANNOT_PROCEED,
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
                detail_code=getattr(exc, "code", "schema_invalid"),
            )
        except _ContextUnavailable as exc:
            calls, timings, outcomes = self._metadata()
            return CaseExecution(
                EvaluationOutcome.CONTEXT_UNAVAILABLE,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                detail_code=str(exc),
            )
        except _ReplayError as exc:
            calls, timings, outcomes = self._metadata()
            outcome = {
                "script_exhausted": EvaluationOutcome.SCRIPT_EXHAUSTED,
                "question_intent_mismatch": EvaluationOutcome.QUESTION_INTENT_MISMATCH,
            }[exc.code]
            return CaseExecution(
                outcome,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                detail_code=exc.code,
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
