"""Host-controlled interactive clarification over ``ReasoningSession``."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Callable, Mapping

from onto4.core import AssessmentContext
from onto4.providers import (
    DecisionProfile,
    FormalizationProvider,
    InterpretationProvider,
    InterpretationRefinementProvider,
    InterpretationRequest,
    TypedDecision,
    TypedDecisionProvider,
)
from onto4.reasoning import (
    ClarificationKind,
    ClarificationQuestion,
    ClarificationPolicy,
    ClarificationTurn,
    InterpretationSpace,
    PipelineDisposition,
    TransitionAwareClarificationPolicy,
)

from .ask import assess_interpretation_per_reading
from .orchestration import (
    ClarificationSession,
    PreparedClarificationTransition,
    ReasoningSession,
    answer_reasoning_clarification,
    issue_reasoning_clarification,
    reassess_reasoning_session_per_reading,
    start_reasoning_session_per_reading,
)


NONE_OF_THE_ABOVE_ANSWERS = frozenset(
    {
        "none_of_the_above",
        "none of the above",
        "ни один вариант мне не подходит",
        "ни один вариант",
    }
)


def _is_none_of_the_above(answer: str) -> bool:
    normalized = answer.strip().lower().rstrip(".!?…")
    return normalized in NONE_OF_THE_ABOVE_ANSWERS


class FirstAdmissibleDecisionProvider(TypedDecisionProvider):
    """Select the sole host-admissible workflow branch without semantics."""

    def decide(self, request) -> TypedDecision:
        if not request.choices:
            raise ValueError("Interactive clarification request has no admissible choices.")
        return TypedDecision(
            profile_id=request.profile,
            profile_version=request.profile_version or "",
            choice=request.choices[0],
        )


@dataclass(frozen=True)
class ModelClarificationPolicy(TransitionAwareClarificationPolicy):
    """Delegate wording to a base policy and semantic updates to a provider."""

    base: ClarificationPolicy
    refinement_provider: InterpretationRefinementProvider

    def questions(self, context):
        questions = getattr(self.base, "questions", None)
        if questions is None:
            question = self.base.choose(context)
            return () if question is None else (question,)
        return questions(context)

    def choose(self, context):
        questions = self.questions(context)
        return questions[0] if questions else None

    def choose_for_kind(self, context, kind: ClarificationKind):
        chooser = getattr(self.base, "choose_for_kind", None)
        if chooser is None:
            question = self.base.choose(context)
            return question if question is not None and question.kind is kind else None
        return chooser(context, kind)

    def successor(
        self,
        *,
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
    ) -> tuple[InterpretationSpace, ClarificationTurn]:
        if _is_none_of_the_above(answer):
            successor = interpretation
        else:
            successor = self.refinement_provider.refine(
                interpretation,
                question,
                answer,
            )
            if successor.source_text != interpretation.source_text:
                raise ValueError(
                    "Clarification refinement changed the source_text snapshot."
                )
            if successor.conceptual_depth is not interpretation.conceptual_depth:
                raise ValueError(
                    "Clarification refinement changed the conceptual depth snapshot."
                )
        return successor, ClarificationTurn(
            previous_interpretation_id=interpretation.id,
            question_id=question.id,
            answer=answer,
            successor_interpretation_id=successor.id,
        )


class ClarificationProgressKind(str, Enum):
    """Host classification of one answered clarification turn."""

    Resolved = "resolved"
    StructuralResolution = "structural_resolution"
    Unresolved = "unresolved"
    New = "new"
    NoEffect = "no_effect"
    Unverified = "unverified"
    Abstained = "abstained"


@dataclass(frozen=True)
class ClarificationProgress:
    question_id: str
    question_key: str
    target_ids: tuple[str, ...]
    answer: str
    kind: ClarificationProgressKind
    new_item_ids: tuple[str, ...] = ()
    new_semantic_signatures: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClarificationProgressLedger:
    """Immutable host record of asked questions and semantic progress."""

    entries: tuple[ClarificationProgress, ...] = ()

    @property
    def asked_question_ids(self) -> frozenset[str]:
        return frozenset(item.question_id for item in self.entries)

    @property
    def asked_question_keys(self) -> frozenset[str]:
        return frozenset(item.question_key for item in self.entries)

    def record(self, entry: ClarificationProgress) -> "ClarificationProgressLedger":
        if entry.question_key in self.asked_question_keys:
            raise ValueError(f"Clarification question {entry.question_id!r} was already answered.")
        return ClarificationProgressLedger(entries=(*self.entries, entry))


def _snapshot_items(interpretation: InterpretationSpace) -> dict[str, object]:
    items: dict[str, object] = {}
    for attribute in ("ambiguities", "presuppositions", "ontologies", "readings"):
        for item in getattr(interpretation, attribute):
            items[item.id] = item
    return items


def _semantic_signature(item: object) -> str:
    if not is_dataclass(item):
        return repr(item)
    content = tuple(
        (field_info.name, getattr(item, field_info.name))
        for field_info in fields(item)
        if field_info.name != "id"
    )
    return f"{type(item).__name__}:{content!r}"


def _question_key(
    interpretation: InterpretationSpace,
    question: ClarificationQuestion,
) -> str:
    items = _snapshot_items(interpretation)
    target_signatures = tuple(
        _semantic_signature(items[target_id]) if target_id in items else f"external:{target_id}"
        for target_id in question.target_ids
    )
    return repr((question.kind.value, target_signatures))


def _classify_progress(
    previous: InterpretationSpace,
    successor: InterpretationSpace,
    question: ClarificationQuestion,
    answer: str,
) -> ClarificationProgress:
    before = _snapshot_items(previous)
    after = _snapshot_items(successor)
    new_item_ids = tuple(sorted(set(after) - set(before)))
    before_signature_counts: dict[str, int] = {}
    for item in before.values():
        signature = _semantic_signature(item)
        before_signature_counts[signature] = before_signature_counts.get(signature, 0) + 1
    after_signature_counts: dict[str, int] = {}
    for item in after.values():
        signature = _semantic_signature(item)
        after_signature_counts[signature] = after_signature_counts.get(signature, 0) + 1
    new_semantic_signatures = tuple(
        sorted(
            signature
            for signature, count in after_signature_counts.items()
            for _ in range(max(0, count - before_signature_counts.get(signature, 0)))
        )
    )
    if _is_none_of_the_above(answer):
        kind = ClarificationProgressKind.Abstained
    elif successor == previous:
        kind = ClarificationProgressKind.NoEffect
    else:
        known_targets = tuple(
            target_id for target_id in question.target_ids if target_id in before
        )
        if not known_targets:
            kind = ClarificationProgressKind.Unverified
        else:
            before_signatures = {
                target_id: _semantic_signature(before[target_id])
                for target_id in known_targets
            }
            after_signatures = {
                _semantic_signature(item) for item in after.values()
            }
            target_preserved = any(
                signature in after_signatures
                for signature in before_signatures.values()
            )
            target_removed = any(
                signature not in after_signatures
                for signature in before_signatures.values()
            )
            same_id_preserved = all(
                target_id in after
                and _semantic_signature(after[target_id]) == signature
                for target_id, signature in before_signatures.items()
            )
            semantic_snapshot_unchanged = (
                before_signature_counts == after_signature_counts
            )
            if semantic_snapshot_unchanged:
                # A host reindex or permutation is not semantic progress.
                kind = ClarificationProgressKind.NoEffect
            elif new_semantic_signatures and target_preserved:
                kind = ClarificationProgressKind.New
            elif target_preserved:
                # A target may be re-indexed by the model.  Its semantic
                # signature, rather than its technical id, is authoritative
                # for progress classification.
                kind = (
                    ClarificationProgressKind.NoEffect
                    if same_id_preserved and not new_semantic_signatures
                    else ClarificationProgressKind.Unresolved
                )
            elif target_removed:
                # A full snapshot can show that the ambiguity disappeared, but
                # it cannot prove that the model selected the meaning intended
                # by the user's free-form answer. Keep this distinct from
                # host-verified ``Resolved`` until an explicit refinement delta
                # is available.
                kind = ClarificationProgressKind.StructuralResolution
            elif new_semantic_signatures:
                kind = ClarificationProgressKind.New
            else:
                kind = ClarificationProgressKind.NoEffect
    return ClarificationProgress(
        question_id=question.id,
        question_key=_question_key(previous, question),
        target_ids=question.target_ids,
        answer=answer,
        kind=kind,
        new_item_ids=new_item_ids,
        new_semantic_signatures=new_semantic_signatures,
    )


@dataclass
class ProgressAwareClarificationPolicy(TransitionAwareClarificationPolicy):
    """Add deterministic question de-duplication and transition admission."""

    base: TransitionAwareClarificationPolicy
    ledger: ClarificationProgressLedger = field(default_factory=ClarificationProgressLedger)

    def choose(self, context):
        questions = getattr(self.base, "questions", None)
        candidates = (
            questions(context)
            if questions is not None
            else tuple(filter(None, (self.base.choose(context),)))
        )
        return next(
            (
                question
                for question in candidates
                if _question_key(context.interpretation, question)
                not in self.ledger.asked_question_keys
            ),
            None,
        )

    def choose_for_kind(self, context, kind: ClarificationKind):
        questions = getattr(self.base, "questions", None)
        if questions is not None:
            return next(
                (
                    question
                    for question in questions(context)
                    if question.kind is kind
                    and _question_key(context.interpretation, question)
                    not in self.ledger.asked_question_keys
                ),
                None,
            )
        question = self.base.choose_for_kind(context, kind)
        if question is None:
            return None
        return (
            None
            if _question_key(context.interpretation, question)
            in self.ledger.asked_question_keys
            else question
        )

    def successor(
        self,
        *,
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
    ) -> tuple[InterpretationSpace, ClarificationTurn]:
        prepared = self.prepare_successor(
            interpretation=interpretation,
            question=question,
            answer=answer,
        )
        self.commit_prepared(prepared)
        return prepared.successor, prepared.turn

    def prepare_successor(
        self,
        *,
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
    ) -> PreparedClarificationTransition:
        successor, turn = self.base.successor(
            interpretation=interpretation,
            question=question,
            answer=answer,
        )
        progress = _classify_progress(interpretation, successor, question, answer)
        if progress.kind in {
            ClarificationProgressKind.NoEffect,
            ClarificationProgressKind.New,
            ClarificationProgressKind.Unverified,
        }:
            raise ValueError(
                "Clarification answer did not affect its target distinction "
                f"(progress={progress.kind.value})."
            )
        return PreparedClarificationTransition(successor, turn, progress)

    def commit_prepared(self, prepared: PreparedClarificationTransition) -> None:
        if not isinstance(prepared.progress, ClarificationProgress):
            raise ValueError("Prepared clarification transition has no progress record.")
        self.ledger = self.ledger.record(prepared.progress)


@dataclass(frozen=True)
class InteractiveDialogueResult:
    session: ReasoningSession
    turns: int
    progress: ClarificationProgressLedger = field(default_factory=ClarificationProgressLedger)
    stop_reason: str | None = None


def interactive_decision_profile() -> DecisionProfile:
    return DecisionProfile(
        id="interactive-clarification",
        version="1",
        choices=(
            "NeedMeaningClarification",
            "NeedOntologyClarification",
            "NeedReferenceClarification",
            "NeedContextClarification",
            "NeedPresuppositionClarification",
            "NeedFormalizationClarification",
        ),
    )


def run_interactive_dialogue(
    request: InterpretationRequest,
    *,
    interpretation_provider: InterpretationProvider,
    refinement_provider: InterpretationRefinementProvider,
    formalization_provider: FormalizationProvider,
    contexts: Mapping[str, AssessmentContext],
    clarification_policy: TransitionAwareClarificationPolicy,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    max_turns: int = 4,
) -> InteractiveDialogueResult:
    """Run bounded clarification, answer, successor and reassessment steps."""

    if max_turns < 1:
        raise ValueError("max_turns must be positive.")
    progress_policy = ProgressAwareClarificationPolicy(clarification_policy)
    interpretation = interpretation_provider.interpret(request)
    current = start_reasoning_session_per_reading(
        ClarificationSession(interpretation),
        formalization_provider=formalization_provider,
        contexts=contexts,
        clarification_policy=progress_policy,
    ).session
    profile = interactive_decision_profile()
    decision_provider = FirstAdmissibleDecisionProvider()

    for turn_index in range(max_turns + 1):
        if current.assessment is None:
            current = reassess_reasoning_session_per_reading(
                current,
                formalization_provider=formalization_provider,
                contexts=contexts,
                clarification_policy=progress_policy,
            ).session
        assessment = current.assessment
        assert assessment is not None
        ask_result = assessment.ask_result
        if ask_result.disposition is not PipelineDisposition.AskClarification:
            stop_reason = {
                PipelineDisposition.Complete: "complete",
                PipelineDisposition.NeedEvidence: "need_evidence",
                PipelineDisposition.CannotProceed: "cannot_proceed",
            }.get(ask_result.disposition, ask_result.disposition.value)
            return InteractiveDialogueResult(
                current,
                turn_index,
                progress_policy.ledger,
                stop_reason,
            )
        if turn_index >= max_turns:
            return InteractiveDialogueResult(
                current,
                turn_index,
                progress_policy.ledger,
                "max_turns_reached",
            )
        if ask_result.clarification_question is None:
            return InteractiveDialogueResult(
                current,
                turn_index,
                progress_policy.ledger,
                "no_new_admissible_question",
            )
        issued = issue_reasoning_clarification(
            current,
            profile=profile,
            provider=decision_provider,
            clarification_policy=progress_policy,
        )
        current = issued.session
        if issued.clarification is None:
            raise ValueError("Clarification issuance returned no decision result.")
        question = issued.clarification.turn_result.decision.question
        if question is None:
            return InteractiveDialogueResult(
                current,
                turn_index,
                progress_policy.ledger,
                "no_new_admissible_question",
            )
        output_fn(f"Clarification: {question.text}")
        if question.choices:
            output_fn("Choices: " + ", ".join(question.choices))
        output_fn("You may answer freely or type 'none_of_the_above'.")
        answer = input_fn("> ")
        if not answer.strip():
            raise ValueError("An interactive clarification answer must not be empty.")
        current = answer_reasoning_clarification(
            current,
            answer=answer,
            clarification_policy=progress_policy,
            allow_freeform_answers=True,
        ).session

    raise AssertionError("Interactive dialogue loop exited unexpectedly.")


__all__ = [
    "FirstAdmissibleDecisionProvider",
    "ClarificationProgress",
    "ClarificationProgressKind",
    "ClarificationProgressLedger",
    "InteractiveDialogueResult",
    "ModelClarificationPolicy",
    "ProgressAwareClarificationPolicy",
    "NONE_OF_THE_ABOVE_ANSWERS",
    "interactive_decision_profile",
    "run_interactive_dialogue",
]
