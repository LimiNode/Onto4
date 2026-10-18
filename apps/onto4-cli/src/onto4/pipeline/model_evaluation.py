"""Model-backed corpus execution using the existing Onto4 orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from time import monotonic
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
from onto4.reasoning import ConceptualDepth, FixtureClarificationPolicy, PipelineDisposition
from onto4.reasoning import ClarificationKind

from .clarification_corpus import ClarificationCorpusCase
from .evaluation import CaseExecution, EvaluationOutcome
from .interactive import ModelClarificationPolicy, run_interactive_dialogue


_SAFE_STAGE_CODES = frozenset({"schema_valid", "transport", "schema", "unexpected"})
_SAFE_STAGE_NAMES = frozenset({"interpretation", "formalization"})
_SAFE_PHASES = frozenset(
    {"started", "response_received", "json_valid", "json_invalid", "completed", "failed"}
)
_SAFE_FINISH_REASONS = frozenset(
    {"stop", "length", "tool_calls", "content_filter", "function_call", "unknown"}
)
_FINISH_DETAIL_RE = re.compile(
    r"^finish_reason=(?P<reason>[A-Za-z0-9_.-]{1,32})"
    r"(?:, completion_tokens=(?P<tokens>[0-9]{1,9}))?$"
)


class _ReplayError(ValueError):
    """A scripted dialogue cannot be safely replayed against this model turn."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _QuestionIntent:
    kind: ClarificationKind | None
    target_family: str | None
    target_ids: tuple[str, ...]


@dataclass(frozen=True)
class _ReplayPolicy(ModelClarificationPolicy):
    """Validate each emitted question against the scripted intent binding."""

    expected_intents: tuple[_QuestionIntent, ...] = ()
    issued_questions: int = 0
    _last_questions: tuple = field(default=(), init=False, compare=False)

    def questions(self, context):
        # Preserve the host policy's order.  Replay admission is performed
        # against the question actually issued by the interactive loop.
        questions = super().questions(context)
        object.__setattr__(self, "_last_questions", tuple(questions))
        return questions

    def validate_issued(self, question) -> None:
        """Validate the concrete host-issued question without reordering it."""

        if self.issued_questions >= len(self.expected_intents):
            raise _ReplayError("script_exhausted")
        expected = self.expected_intents[self.issued_questions]
        if expected.kind is None or not expected.target_family or not expected.target_ids:
            raise _ReplayError("question_intent_unverified")
        if question.target_family is None:
            raise _ReplayError("question_intent_unverified")
        if question.kind is not expected.kind:
            raise _ReplayError("question_intent_mismatch")
        if question.target_family != expected.target_family:
            raise _ReplayError("question_intent_mismatch")
        candidates = tuple(
            candidate
            for candidate in self._last_questions
            if candidate.kind is expected.kind
            and candidate.target_family == expected.target_family
        )
        if not candidates:
            raise _ReplayError("question_intent_mismatch")
        if len(candidates) == 1:
            return
        if tuple(question.target_ids) == expected.target_ids:
            return
        raise _ReplayError("question_intent_unverified")

    def choose_for_kind(self, context, kind: ClarificationKind):
        return super().choose_for_kind(context, kind)

    def mark_issued(self) -> None:
        object.__setattr__(self, "issued_questions", self.issued_questions + 1)


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
    requested_conceptual_depth: ConceptualDepth | None = None
    trace_sink: ProviderTrace | None = None
    _last_events: list[ProviderStageEvent] = field(default_factory=list, init=False)

    def _trace(self, event: ProviderStageEvent) -> None:
        self._last_events.append(event)
        if self.trace_sink is not None:
            self.trace_sink(event)

    def _metadata(
        self,
    ) -> tuple[int, dict[str, float], dict[str, str], dict[str, str]]:
        timings: dict[str, float] = {}
        outcomes: dict[str, str] = {}
        details: dict[str, str] = {}
        calls = 0
        occurrences: dict[str, int] = {}
        active_keys: dict[str, str] = {}
        for event in self._last_events:
            stage = self._safe_stage_name(event.stage)
            phase = self._safe_phase(event.phase)
            if phase == "started":
                calls += 1
                occurrences[stage] = occurrences.get(stage, 0) + 1
                suffix = occurrences[stage]
                active_keys[stage] = (
                    stage if suffix == 1 else f"{stage}#{suffix}"
                )
            key = active_keys.get(stage, stage)
            if event.elapsed_seconds:
                # A stage emits several observational events; the final event
                # carries the full elapsed duration, so do not double-count
                # intermediate response/json markers.
                timings[key] = max(
                    timings.get(key, 0.0), event.elapsed_seconds
                )
            outcomes[key] = phase
            if event.detail:
                safe_detail = self._safe_stage_detail(event.detail)
                if safe_detail is not None:
                    previous = details.get(key)
                    details[key] = (
                        safe_detail
                        if previous is None
                        else f"{previous}; {safe_detail}"
                    )
        return calls, timings, outcomes, details

    @staticmethod
    def _safe_stage_name(stage: object) -> str:
        return stage if isinstance(stage, str) and stage in _SAFE_STAGE_NAMES else "other"

    @staticmethod
    def _safe_phase(phase: object) -> str:
        return phase if isinstance(phase, str) and phase in _SAFE_PHASES else "other"

    @staticmethod
    def _safe_stage_detail(detail: str) -> str | None:
        if not isinstance(detail, str) or len(detail) > 128:
            return None
        if detail in _SAFE_STAGE_CODES:
            return detail
        match = _FINISH_DETAIL_RE.fullmatch(detail)
        if match is None:
            return None
        reason = match.group("reason")
        normalized_reason = reason if reason in _SAFE_FINISH_REASONS else "other"
        tokens = match.group("tokens")
        return (
            f"finish_reason={normalized_reason}"
            + (f", completion_tokens={tokens}" if tokens is not None else "")
        )

    @staticmethod
    def _diagnostics(
        ask_result,
        *,
        pending: bool = False,
        clarification_issued: bool = False,
    ) -> dict[str, object]:
        interpretation = ask_result.interpretation
        return {
            "landscape_status": ask_result.landscape.status.value,
            "disposition": ask_result.disposition.value,
            "reason": ask_result.reason,
            "reading_count": len(interpretation.readings),
            "ambiguity_count": len(interpretation.ambiguities),
            "pending_clarification": pending,
            "clarification_issued": clarification_issued,
        }

    def _request(self, case: ClarificationCorpusCase) -> InterpretationRequest:
        state = {
            "evaluation_case_id": case.case_id,
            "model_input": case.model_input,
        }
        if case.model_input == "contextual" and case.context is not None:
            state["context_id"] = case.context
        return InterpretationRequest(
            case.utterance,
            conceptual_depth=self.requested_conceptual_depth,
            state=state,
        )

    def _case_contexts(self, case: ClarificationCorpusCase) -> Mapping[str, AssessmentContext]:
        if case.context is None:
            return self.contexts
        try:
            return {case.context: self.contexts[case.context]}
        except KeyError as exc:
            raise _ContextUnavailable("context_unavailable") from exc

    def _set_provider_deadline(self, deadline: float | None) -> None:
        seen: set[int] = set()
        for provider in (self.interpretation_provider, self.formalization_provider):
            client = getattr(provider, "client", None)
            if client is None or id(client) in seen:
                continue
            seen.add(id(client))
            setter = getattr(client, "set_deadline", None)
            if setter is not None:
                setter(deadline)

    @staticmethod
    def _script(
        case: ClarificationCorpusCase,
    ) -> tuple[list[str], int, tuple[_QuestionIntent, ...]]:
        if not case.dialogue:
            return [], 0, ()
        turns = list(case.dialogue)
        if turns[0].get("role") != "user" or turns[0].get("text") != case.utterance:
            raise _ReplayError("question_intent_mismatch")
        answers: list[str] = []
        question_intents: list[_QuestionIntent] = []
        expected_role = "user"
        for index, turn in enumerate(turns):
            role = turn.get("role")
            if role != expected_role:
                raise _ReplayError("question_intent_mismatch")
            expected_role = "assistant" if role == "user" else "user"
            if role == "assistant":
                raw_kind = turn.get("question_kind")
                kind: ClarificationKind | None = None
                if isinstance(raw_kind, str):
                    try:
                        kind = ClarificationKind(raw_kind)
                    except ValueError:
                        raise _ReplayError("question_intent_mismatch") from None
                raw_target_ids = turn.get("target_ids")
                target_ids = (
                    tuple(raw_target_ids)
                    if isinstance(raw_target_ids, list)
                    and all(isinstance(item, str) and item for item in raw_target_ids)
                    else ()
                )
                target_family = turn.get("target_family")
                if raw_kind is not None or "target_family" in turn or "target_ids" in turn:
                    question_intents.append(
                        _QuestionIntent(
                            kind,
                            target_family if isinstance(target_family, str) else None,
                            target_ids,
                        )
                    )
            elif index:
                answers.append(str(turn.get("text", "")))
        return answers, len(question_intents), tuple(question_intents)

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
        self._last_events = []
        self._set_provider_deadline(monotonic() + request_timeout_seconds)
        try:
            request = self._request(case)
            case_contexts = self._case_contexts(case)
            if case.mode == "dialogue" and not case.dialogue:
                raise _ReplayError("script_exhausted")
            if case.mode == "dialogue" and case.dialogue:
                answers, scripted_questions, scripted_intents = self._script(case)
                expected_kind = self._expected_kind(case)
                expected_intents = scripted_intents or (
                    (_QuestionIntent(expected_kind, None, ()),) if expected_kind else ()
                )
                answer_index = 0

                def validate_question(_, question) -> None:
                    policy.validate_issued(question)

                def input_fn(_: str) -> str:
                    nonlocal answer_index
                    policy.mark_issued()
                    if answer_index >= len(answers):
                        raise _ReplayError("script_exhausted")
                    answer = answers[answer_index]
                    answer_index += 1
                    return answer

                policy = _ReplayPolicy(
                    FixtureClarificationPolicy(),
                    self.interpretation_provider,
                    expected_intents=expected_intents,
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
                    before_answer_fn=validate_question,
                    max_turns=self.max_turns,
                )
                if (
                    result.stop_reason == "complete"
                    and case.expected_clarification is not None
                    and policy.issued_questions == 0
                ):
                    raise _ReplayError("question_intent_mismatch")
                if (
                    result.stop_reason == "complete"
                    and policy.issued_questions < len(expected_intents)
                ):
                    assessment = result.session.assessment
                    return CaseExecution(
                        EvaluationOutcome.DIALOGUE_INCOMPLETE,
                        provider_calls=self._metadata()[0],
                        stage_timings=self._metadata()[1],
                        stage_outcomes=self._metadata()[2],
                        stage_details=self._metadata()[3],
                        detail_code="required_question_not_issued",
                        diagnostics=(
                            self._diagnostics(
                                assessment.ask_result,
                                pending=result.session.clarification.pending is not None,
                                clarification_issued=bool(result.progress.entries),
                            )
                            if assessment is not None
                            else {}
                        ),
                    )
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
            calls, timings, outcomes, details = self._metadata()
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
                stage_details=details,
                semantic_verdict=verdict,
                detail_code="model_backed",
                diagnostics=self._diagnostics(
                    ask_result,
                    pending=(
                        result.session.clarification.pending is not None
                        if case.mode == "dialogue"
                        else False
                    ),
                    clarification_issued=(
                        bool(result.progress.entries) if case.mode == "dialogue" else False
                    ),
                ) if ask_result is not None else {},
            )
        except ProviderTransportError as exc:
            calls, timings, outcomes, details = self._metadata()
            return CaseExecution(
                EvaluationOutcome.TRANSPORT_ERROR,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                stage_details=details,
                detail_code=type(exc).__name__,
            )

        except ProviderSchemaError as exc:
            calls, timings, outcomes, details = self._metadata()
            return CaseExecution(
                EvaluationOutcome.SCHEMA_INVALID,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                stage_details=details,
                detail_code=getattr(exc, "code", "schema_invalid"),
            )
        except _ContextUnavailable as exc:
            calls, timings, outcomes, details = self._metadata()
            return CaseExecution(
                EvaluationOutcome.CONTEXT_UNAVAILABLE,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                stage_details=details,
                detail_code=str(exc),
            )
        except _ReplayError as exc:
            calls, timings, outcomes, details = self._metadata()
            outcome = {
                "script_exhausted": EvaluationOutcome.SCRIPT_EXHAUSTED,
                "question_intent_mismatch": EvaluationOutcome.QUESTION_INTENT_MISMATCH,
                "question_intent_unverified": EvaluationOutcome.QUESTION_INTENT_UNVERIFIED,
            }[exc.code]
            return CaseExecution(
                outcome,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                stage_details=details,
                detail_code=exc.code,
            )
        except (KeyError, ValueError) as exc:
            calls, timings, outcomes, details = self._metadata()
            return CaseExecution(
                EvaluationOutcome.PROVENANCE_INVALID,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                stage_details=details,
                detail_code=type(exc).__name__,
            )
        finally:
            self._set_provider_deadline(None)

    def provider_trace(self, event: ProviderStageEvent) -> None:
        """Collect one adapter event for the current case and forward it safely."""

        self._trace(event)


__all__ = ["ModelCaseExecutor"]
