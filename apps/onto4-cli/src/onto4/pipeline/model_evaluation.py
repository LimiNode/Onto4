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
    RefinementDeltaProvider,
    project_assessment_context,
)
from onto4.providers.diagnostics import ProviderStageEvent, ProviderTrace
from onto4.reasoning import (
    ConceptualDepth,
    FixtureClarificationPolicy,
    PipelineDisposition,
    TransitionAwareClarificationPolicy,
)
from onto4.reasoning import ClarificationKind

from .clarification_corpus import ClarificationCorpusCase
from .evaluation import CaseExecution, EvaluationOutcome
from .interactive import (
    ModelClarificationPolicy,
    TypedDeltaClarificationPolicy,
    run_interactive_dialogue,
)
from .refinement import RefinementUnsupportedError


_SAFE_STAGE_CODES = frozenset({"schema_valid", "transport", "schema", "unexpected"})
_SAFE_STAGE_NAMES = frozenset({"interpretation", "formalization", "refinement"})
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


def _safe_target_family(value: object) -> str | None:
    """Publish only structural target classes, never user/model terms."""

    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    if normalized in {"candidate", "context", "reading", "ambiguity", "ontology"}:
        return normalized
    return "opaque"


class _ReplayError(ValueError):
    """A scripted dialogue cannot be safely replayed against this model turn."""

    def __init__(self, code: str, reason: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class _QuestionIntent:
    kind: ClarificationKind | None
    target_family: str | None
    target_ids: tuple[str, ...]


@dataclass(frozen=True)
class _ReplayPolicy:
    """Validate each emitted question against the scripted intent binding."""

    base: TransitionAwareClarificationPolicy
    expected_intents: tuple[_QuestionIntent, ...] = ()
    issued_questions: int = 0
    telemetry: dict[str, object] = field(default_factory=dict, compare=False)
    _last_questions: tuple = field(default=(), init=False, compare=False)

    def questions(self, context):
        # Preserve the host policy's order.  Replay admission is performed
        # against the question actually issued by the interactive loop.
        questions_method = getattr(self.base, "questions", None)
        questions = (
            questions_method(context)
            if questions_method is not None
            else tuple(filter(None, (self.base.choose(context),)))
        )
        object.__setattr__(self, "_last_questions", tuple(questions))
        self.telemetry["question_candidate_generated"] = True
        self.telemetry["question_candidate_count"] = len(questions)
        self.telemetry["last_stage"] = "question_candidate_generated"
        return questions

    def validate_issued(self, question) -> None:
        """Validate the concrete host-issued question without reordering it."""
        self.telemetry["question_selected"] = True
        self.telemetry["last_stage"] = "question_selected"
        if self.issued_questions >= len(self.expected_intents):
            self.telemetry["intent_admitted"] = False
            raise _ReplayError("script_exhausted", "script_exhausted")
        expected = self.expected_intents[self.issued_questions]
        if expected.kind is None or not expected.target_family or not expected.target_ids:
            self.telemetry["intent_admitted"] = False
            raise _ReplayError("question_intent_unverified", "intent_unverified")
        if question.target_family is None:
            self.telemetry["intent_admitted"] = False
            raise _ReplayError("question_intent_unverified", "family_unverified")
        if question.kind is not expected.kind:
            self.telemetry["intent_admitted"] = False
            raise _ReplayError("question_intent_mismatch", "kind_mismatch")
        if question.target_family != expected.target_family:
            self.telemetry["intent_admitted"] = False
            raise _ReplayError("question_intent_mismatch", "family_mismatch")
        candidates = tuple(
            candidate
            for candidate in self._last_questions
            if candidate.kind is expected.kind
            and candidate.target_family == expected.target_family
        )
        if not candidates:
            self.telemetry["intent_admitted"] = False
            raise _ReplayError("question_intent_mismatch", "no_candidate")
        if len(candidates) == 1:
            self.telemetry["intent_admitted"] = True
            self.telemetry["last_stage"] = "intent_admitted"
            return
        if tuple(question.target_ids) == expected.target_ids:
            self.telemetry["intent_admitted"] = True
            self.telemetry["last_stage"] = "intent_admitted"
            return
        self.telemetry["intent_admitted"] = False
        raise _ReplayError(
            "question_intent_unverified",
            "target_ambiguous" if not question.target_ids else "target_mismatch",
        )

    def choose(self, context):
        questions = self.questions(context)
        return questions[0] if questions else None

    def choose_for_kind(self, context, kind: ClarificationKind):
        question = self.base.choose_for_kind(context, kind)
        self.telemetry["question_candidate_generated"] = question is not None
        self.telemetry["question_candidate_count"] = 0 if question is None else 1
        self.telemetry["last_stage"] = "question_candidate_generated"
        if question is not None:
            self.telemetry["question_selected"] = True
            self.telemetry["last_stage"] = "question_selected"
            # Admission is recorded at selection time so a rejected question
            # still leaves an honest candidate/selection trace. The callback
            # before answer repeats this check against the same immutable
            # question and does not issue it a second time.
            self.validate_issued(question)
        return question

    def record_question_selected(self, question) -> None:
        """Record selection/admission before the interactive answer callback."""

        self.telemetry["question_selected"] = True
        self.telemetry["last_stage"] = "question_selected"
        self.validate_issued(question)

    def successor(self, *, interpretation, question, answer):
        result = self.base.successor(
            interpretation=interpretation,
            question=question,
            answer=answer,
        )
        self.telemetry["refinement_accepted"] = True
        self.telemetry["last_stage"] = "refinement_accepted"
        return result

    def prepare_successor(self, *, interpretation, question, answer):
        prepare = getattr(self.base, "prepare_successor", None)
        if prepare is None:
            return None
        result = prepare(
            interpretation=interpretation,
            question=question,
            answer=answer,
        )
        self.telemetry["refinement_accepted"] = True
        self.telemetry["last_stage"] = "refinement_accepted"
        return result

    def mark_issued(self) -> None:
        object.__setattr__(self, "issued_questions", self.issued_questions + 1)
        self.telemetry["question_issued"] = True
        self.telemetry["last_stage"] = "question_issued"


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
    interpretation_context_mode: str = "context_late"
    refinement_mode: str = "full_snapshot"
    refinement_delta_provider: RefinementDeltaProvider | None = None
    trace_sink: ProviderTrace | None = None
    _last_events: list[ProviderStageEvent] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.interpretation_context_mode not in {"context_late", "context_aware"}:
            raise ValueError(
                "interpretation_context_mode must be context_late or context_aware."
            )
        if self.refinement_mode not in {"full_snapshot", "typed_delta"}:
            raise ValueError("refinement_mode must be full_snapshot or typed_delta.")
        if self.refinement_mode == "typed_delta" and self.refinement_delta_provider is None:
            raise ValueError("typed_delta mode requires a refinement_delta_provider.")

    def _refinement_policy(self) -> TransitionAwareClarificationPolicy:
        base = FixtureClarificationPolicy()
        if self.refinement_mode == "typed_delta":
            assert self.refinement_delta_provider is not None
            return TypedDeltaClarificationPolicy(base, self.refinement_delta_provider)
        return ModelClarificationPolicy(base, self.interpretation_provider)

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
        progress=None,
    ) -> dict[str, object]:
        interpretation = ask_result.interpretation
        entries = tuple(getattr(progress, "entries", ()))
        operation_counts: dict[str, int] = {}
        effect_counts: dict[str, int] = {}
        committed = 0
        proposed = 0
        for entry in entries:
            for operation in getattr(entry, "refinement_operations", ()):
                operation_counts[operation] = operation_counts.get(operation, 0) + 1
            for effect in getattr(entry, "refinement_effects", ()):
                effect_counts[effect] = effect_counts.get(effect, 0) + 1
            committed += int(bool(getattr(entry, "refinement_committed", False)))
            proposed += int(getattr(entry, "refinement_proposed_count", 0))
        return {
            "landscape_status": ask_result.landscape.status.value,
            "disposition": ask_result.disposition.value,
            "reason": ask_result.reason,
            "reading_count": len(interpretation.readings),
            "ambiguity_count": len(interpretation.ambiguities),
            "pending_clarification": pending,
            "clarification_issued": clarification_issued,
            "clarification_turns": len(entries),
            "refinement_operations": operation_counts,
            "refinement_effects": effect_counts,
            "refinement_commits": committed,
            "refinement_proposed": proposed,
        }

    def _request(self, case: ClarificationCorpusCase) -> InterpretationRequest:
        state = {
            "evaluation_case_id": case.case_id,
            "model_input": case.model_input,
        }
        if case.model_input == "contextual" and case.context is not None:
            state["context_id"] = case.context
        if (
            self.interpretation_context_mode == "context_aware"
            and case.model_input == "contextual"
            and case.context is not None
            and case.context in self.contexts
        ):
            state["context_projections"] = {
                case.context: project_assessment_context(
                    case.context, self.contexts[case.context]
                ).as_dict()
            }
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
        for provider in (
            self.interpretation_provider,
            self.formalization_provider,
            self.refinement_delta_provider,
        ):
            if provider is None:
                continue
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
        workflow: dict[str, object] = {
            "last_stage": "started",
            "questions_issued": 0,
            "answers_consumed": 0,
            "refinement_accepted": False,
            "reassessment_performed": False,
            "clarification_turns": None,
            "clarification_turns_known": False,
        }

        def with_workflow(diagnostics: Mapping[str, object] | None = None) -> dict[str, object]:
            result = dict(diagnostics or {})
            result.update(workflow)
            return result

        try:
            request = self._request(case)
            workflow["last_stage"] = "request_built"
            case_contexts = self._case_contexts(case)
            workflow["last_stage"] = "contexts_bound"
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
                    expected_intent = expected_intents[policy.issued_questions]
                    telemetry = {
                        "questions_issued": int(workflow["questions_issued"]) + 1,
                        "question_id": question.id,
                        "question_kind": question.kind.value,
                        "question_target_family": _safe_target_family(question.target_family),
                        "question_script_target_family_match": (
                            question.target_family == expected_intent.target_family
                        ),
                        "question_target_ids": tuple(question.target_ids),
                        "last_stage": "question_issued",
                    }
                    expected_clarification = case.expected_clarification
                    if isinstance(expected_clarification, Mapping):
                        expected_family = expected_clarification.get("target_family")
                        if isinstance(expected_family, str) and expected_family.strip():
                            telemetry["question_target_family_match"] = (
                                question.target_family == expected_family
                            )
                    workflow.update(telemetry)

                def input_fn(_: str) -> str:
                    nonlocal answer_index
                    policy.mark_issued()
                    if answer_index >= len(answers):
                        raise _ReplayError("script_exhausted")
                    answer = answers[answer_index]
                    answer_index += 1
                    workflow.update(
                        {
                            "answers_consumed": int(workflow["answers_consumed"]) + 1,
                            "last_stage": "answer_consumed",
                        }
                    )
                    return answer

                policy = _ReplayPolicy(
                    self._refinement_policy(),
                    expected_intents=expected_intents,
                    telemetry=workflow,
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
                workflow.update(
                    {
                        "clarification_turns": len(result.progress.entries),
                        "clarification_turns_known": True,
                        "reassessment_performed": bool(
                            result.progress.entries and result.session.assessment is not None
                        ),
                        "last_stage": (
                            "reassessment_completed"
                            if result.progress.entries and result.session.assessment is not None
                            else "initial_assessment_completed"
                        ),
                    }
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
                        diagnostics=with_workflow(
                            self._diagnostics(
                                assessment.ask_result,
                                pending=result.session.clarification.pending is not None,
                                clarification_issued=bool(result.progress.entries),
                                progress=result.progress,
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
                workflow.update(
                    {
                        "clarification_turns": 0,
                        "clarification_turns_known": True,
                        "reassessment_performed": True,
                        "last_stage": "assessment_completed",
                    }
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
                diagnostics=with_workflow(self._diagnostics(
                    ask_result,
                    pending=(
                        result.session.clarification.pending is not None
                        if case.mode == "dialogue"
                        else False
                    ),
                    clarification_issued=(
                        bool(result.progress.entries) if case.mode == "dialogue" else False
                    ),
                    progress=(result.progress if case.mode == "dialogue" else None),
                )) if ask_result is not None else with_workflow(),
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
                diagnostics=with_workflow(),
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
                diagnostics=with_workflow(),
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
                diagnostics=with_workflow(),
            )
        except RefinementUnsupportedError as exc:
            calls, timings, outcomes, details = self._metadata()
            return CaseExecution(
                EvaluationOutcome.UNSUPPORTED_DIALOGUE_STEP,
                provider_calls=calls,
                stage_timings=timings,
                stage_outcomes=outcomes,
                stage_details=details,
                detail_code="typed_delta_unsupported",
                diagnostics=with_workflow(),
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
                detail_code=exc.reason or exc.code,
                diagnostics=with_workflow({
                    "question_intent_failure_reason": exc.reason or exc.code,
                }),
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
                diagnostics=with_workflow(),
            )
        finally:
            self._set_provider_deadline(None)

    def provider_trace(self, event: ProviderStageEvent) -> None:
        """Collect one adapter event for the current case and forward it safely."""

        self._trace(event)


__all__ = ["ModelCaseExecutor"]
