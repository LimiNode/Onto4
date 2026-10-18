"""Host-controlled interactive clarification over ``ReasoningSession``."""

from __future__ import annotations

import hashlib
import json
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
    RefinementDeltaProvider,
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
    SemanticReading,
    TransitionAwareClarificationPolicy,
)

from .ask import assess_interpretation_per_reading
from .refinement import (
    RefinementDelta,
    RefinementEffect,
    RefinementOperation,
    RefinementRequest,
    RefinementTransitionEvidence,
    RefinementUnsupportedError,
    RefinementValidationError,
    apply_refinement_batch,
    apply_refinement_delta,
)
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


@dataclass(frozen=True)
class TypedDeltaClarificationPolicy(TransitionAwareClarificationPolicy):
    """Apply model-proposed operations through the host refinement boundary."""

    base: ClarificationPolicy
    refinement_provider: RefinementDeltaProvider

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

    @staticmethod
    def _request(
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
    ) -> RefinementRequest:
        targets = frozenset(question.target_ids)
        reading_ids = frozenset(item.id for item in interpretation.readings)
        ambiguity_ids = frozenset(
            item.id for item in interpretation.ambiguities if item.id in targets
        )
        allowed_reading_ids = (
            reading_ids if ambiguity_ids else reading_ids & targets
        )
        return RefinementRequest(
            interpretation=interpretation,
            assessment_interpretation_id=interpretation.id,
            allowed_reading_ids=allowed_reading_ids,
            allowed_ambiguity_ids=ambiguity_ids,
            allowed_ontology_ids=frozenset(
                item.id for item in interpretation.ontologies if item.id in targets
            ),
            allowed_presupposition_ids=frozenset(
                item.id for item in interpretation.presuppositions if item.id in targets
            ),
        )

    @staticmethod
    def _successor_id(
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
        deltas: tuple[RefinementDelta, ...],
    ) -> str:
        encoded = json.dumps(
            {
                "interpretation_id": interpretation.id,
                "question_id": question.id,
                "answer": answer,
                "deltas": [
                    {
                        "operation": delta.operation.value,
                        "target_id": delta.target_id,
                        "text": delta.text,
                        "label": delta.label,
                        "description": delta.description,
                        "reason": delta.reason,
                        "reading_id": delta.reading_id,
                        "resolved_ambiguity_ids": list(delta.resolved_ambiguity_ids),
                    }
                    for delta in deltas
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        return f"interpretation-{digest}"

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
        return prepared.successor, prepared.turn

    def prepare_successor(
        self,
        *,
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
    ) -> PreparedClarificationTransition:
        request = self._request(interpretation, question)
        if _is_none_of_the_above(answer):
            deltas = (
                RefinementDelta(
                    RefinementOperation.ABSTAIN, reason="none_of_the_above"
                ),
            )
        else:
            allowed_operations = [
                RefinementOperation.ABSTAIN.value,
            ]
            if request.allowed_ambiguity_ids or (
                question.target_family == "reading" and request.allowed_reading_ids
            ):
                allowed_operations.append(
                    RefinementOperation.ADD_PRESUPPOSITION.value
                )
            if request.allowed_reading_ids:
                allowed_operations.append(RefinementOperation.SELECT_READING.value)
            if request.allowed_ambiguity_ids:
                allowed_operations.extend(
                    (
                        RefinementOperation.RETAIN_AMBIGUITY.value,
                        RefinementOperation.REFINE_AMBIGUITY.value,
                    )
                )
            if request.allowed_ontology_ids:
                allowed_operations.append(
                    RefinementOperation.QUALIFY_ONTOLOGY_CANDIDATE.value
                )
            meaningful = set(allowed_operations) - {RefinementOperation.ABSTAIN.value}
            if not meaningful:
                raise RefinementUnsupportedError(
                    f"Typed delta refinement does not support clarification kind "
                    f"{question.kind.value!r} with target family {question.target_family!r}."
                )
            proposals = self.refinement_provider.propose_refinement_deltas(
                interpretation,
                question,
                answer,
                allowed_operations=tuple(allowed_operations),
                allowed_reading_ids=tuple(sorted(request.allowed_reading_ids)),
                allowed_ambiguity_ids=tuple(sorted(request.allowed_ambiguity_ids)),
                allowed_ontology_ids=tuple(sorted(request.allowed_ontology_ids)),
            )
            deltas = tuple(
                RefinementDelta.from_mapping(proposal) for proposal in proposals
            )
            if any(
                delta.operation is RefinementOperation.ADD_PRESUPPOSITION
                and delta.reading_id is None
                for delta in deltas
            ):
                raise RefinementValidationError(
                    "Typed add_presupposition requires a host-bound reading_id."
                )
        successor_id = self._successor_id(
            interpretation, question, answer, deltas
        )
        if len(deltas) == 1 and deltas[0].operation in {
            RefinementOperation.ABSTAIN,
            RefinementOperation.RETAIN_AMBIGUITY,
        }:
            result = apply_refinement_delta(
                request,
                deltas[0],
                successor_id=successor_id,
            )
            successor = result.successor
            evidence = RefinementTransitionEvidence(
                operations=(deltas[0].operation,),
                effects=(result.commitment.effect,),
                proposed_count=len(deltas),
            )
        else:
            result = apply_refinement_batch(
                request,
                deltas,
                successor_id=successor_id,
            )
            successor = result.successor
            evidence = RefinementTransitionEvidence(
                operations=tuple(item.operation for item in deltas),
                effects=tuple(item.effect for item in result.commitments),
                proposed_count=len(deltas),
            )
        turn = ClarificationTurn(
            previous_interpretation_id=interpretation.id,
            question_id=question.id,
            answer=answer,
            successor_interpretation_id=successor.id,
        )
        return PreparedClarificationTransition(
            successor,
            turn,
            metadata=evidence,
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
    Retained = "retained"


@dataclass(frozen=True)
class ClarificationProgress:
    question_id: str
    question_key: str
    target_ids: tuple[str, ...]
    answer: str
    kind: ClarificationProgressKind
    new_item_ids: tuple[str, ...] = ()
    new_semantic_signatures: tuple[str, ...] = ()
    refinement_operations: tuple[str, ...] = ()
    refinement_effects: tuple[str, ...] = ()
    refinement_committed: bool = False
    refinement_proposed_count: int = 0


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


def _semantic_signature(
    item: object,
    *,
    references: Mapping[str, object] | None = None,
) -> str:
    if not is_dataclass(item):
        return repr(item)
    content = tuple(
        (
            field_info.name,
            (
                tuple(
                    sorted(
                        _semantic_signature(references[target_id], references=references)
                        if references is not None and target_id in references
                        else target_id
                        for target_id in getattr(item, field_info.name)
                    )
                )
                if isinstance(item, SemanticReading)
                and field_info.name == "presupposition_ids"
                else getattr(item, field_info.name)
            ),
        )
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
        _semantic_signature(items[target_id], references=items)
        if target_id in items
        else f"external:{target_id}"
        for target_id in question.target_ids
    )
    return repr((question.kind.value, target_signatures))


def _classify_progress(
    previous: InterpretationSpace,
    successor: InterpretationSpace,
    question: ClarificationQuestion,
    answer: str,
    metadata: object | None = None,
) -> ClarificationProgress:
    before = _snapshot_items(previous)
    after = _snapshot_items(successor)
    new_item_ids = tuple(sorted(set(after) - set(before)))
    before_signature_counts: dict[str, int] = {}
    for item in before.values():
        signature = _semantic_signature(item, references=before)
        before_signature_counts[signature] = before_signature_counts.get(signature, 0) + 1
    after_signature_counts: dict[str, int] = {}
    for item in after.values():
        signature = _semantic_signature(item, references=after)
        after_signature_counts[signature] = after_signature_counts.get(signature, 0) + 1
    new_semantic_signatures = tuple(
        sorted(
            signature
            for signature, count in after_signature_counts.items()
            for _ in range(max(0, count - before_signature_counts.get(signature, 0)))
        )
    )
    evidence = (
        metadata if isinstance(metadata, RefinementTransitionEvidence) else None
    )
    if evidence is not None and all(
        effect is RefinementEffect.ABSTAINED for effect in evidence.effects
    ):
        kind = ClarificationProgressKind.Abstained
    elif evidence is not None and all(
        operation is RefinementOperation.RETAIN_AMBIGUITY
        for operation in evidence.operations
    ):
        kind = ClarificationProgressKind.Retained
    elif _is_none_of_the_above(answer):
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
                target_id: _semantic_signature(before[target_id], references=before)
                for target_id in known_targets
            }
            target_signature_counts = {
                signature: before_signature_counts[signature]
                for signature in before_signatures.values()
            }
            target_multiplicity_changed = any(
                after_signature_counts.get(signature, 0) != count
                for signature, count in target_signature_counts.items()
            )
            after_signatures = {
                _semantic_signature(item, references=after) for item in after.values()
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
                and _semantic_signature(after[target_id], references=after) == signature
                for target_id, signature in before_signatures.items()
            )
            semantic_snapshot_unchanged = (
                before_signature_counts == after_signature_counts
            )
            if semantic_snapshot_unchanged:
                # A host reindex or permutation is not semantic progress.
                kind = ClarificationProgressKind.NoEffect
            elif target_multiplicity_changed and any(
                max(
                    count,
                    after_signature_counts.get(signature, 0),
                )
                > 1
                for signature, count in target_signature_counts.items()
            ):
                # Removing or retaining one of several semantically identical
                # targets does not identify which technical target was answered.
                # Do not claim a verified resolution from multiplicity alone.
                kind = ClarificationProgressKind.Unverified
            elif (
                evidence is not None
                and any(
                    operation
                    in {
                        RefinementOperation.REFINE_AMBIGUITY,
                        RefinementOperation.QUALIFY_ONTOLOGY_CANDIDATE,
                    }
                    for operation in evidence.operations
                )
                and any(effect is RefinementEffect.APPLIED for effect in evidence.effects)
            ):
                # Host-admitted content changes do not establish that the
                # user's intended reading or ontology was selected. They
                # remain unresolved even when the old signature disappears.
                kind = ClarificationProgressKind.Unresolved
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
        refinement_operations=(
            tuple(item.value for item in evidence.operations)
            if evidence is not None
            else ()
        ),
        refinement_effects=(
            tuple(item.value for item in evidence.effects) if evidence is not None else ()
        ),
        refinement_committed=evidence.committed if evidence is not None else False,
        refinement_proposed_count=evidence.proposed_count if evidence is not None else 0,
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
        selected = next(
            (
                question
                for question in candidates
                if _question_key(context.interpretation, question)
                not in self.ledger.asked_question_keys
            ),
            None,
        )
        record = getattr(self.base, "record_question_selected", None)
        if selected is not None and record is not None:
            record(selected)
        return selected

    def choose_for_kind(self, context, kind: ClarificationKind):
        questions = getattr(self.base, "questions", None)
        if questions is not None:
            selected = next(
                (
                    question
                    for question in questions(context)
                    if question.kind is kind
                    and _question_key(context.interpretation, question)
                    not in self.ledger.asked_question_keys
                ),
                None,
            )
            record = getattr(self.base, "record_question_selected", None)
            if selected is not None and record is not None:
                record(selected)
            return selected
        question = self.base.choose_for_kind(context, kind)
        if question is None:
            return None
        selected = (
            None
            if _question_key(context.interpretation, question)
            in self.ledger.asked_question_keys
            else question
        )
        record = getattr(self.base, "record_question_selected", None)
        if selected is not None and record is not None:
            record(selected)
        return selected

    def successor(
        self,
        *,
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
    ) -> tuple[InterpretationSpace, ClarificationTurn]:
        """Apply and record one validated transition.

        This convenience API is intentionally equivalent to
        ``prepare_successor()`` followed by ``commit_prepared()``.  Session,
        pending-question and assessment snapshot provenance remains owned by
        the orchestration layer; callers that have a session must use that
        layer before invoking this low-level transition API.
        """
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
        if not answer:
            raise ValueError("A clarification answer must not be empty.")
        base_prepare = getattr(self.base, "prepare_successor", None)
        base_prepared = (
            base_prepare(
                interpretation=interpretation,
                question=question,
                answer=answer,
            )
            if base_prepare is not None
            else None
        )
        if base_prepared is None:
            successor, turn = self.base.successor(
                interpretation=interpretation,
                question=question,
                answer=answer,
            )
            metadata = None
        else:
            successor, turn = base_prepared.successor, base_prepared.turn
            metadata = base_prepared.metadata
        expected_turn = ClarificationTurn(
            previous_interpretation_id=interpretation.id,
            question_id=question.id,
            answer=answer,
            successor_interpretation_id=successor.id,
        )
        if turn != expected_turn:
            raise ValueError(
                "Clarification transition returned inconsistent turn provenance."
            )
        progress = _classify_progress(
            interpretation, successor, question, answer, metadata
        )
        if progress.kind in {
            ClarificationProgressKind.NoEffect,
            ClarificationProgressKind.Unverified,
        }:
            raise ValueError(
                "Clarification answer did not affect its target distinction "
                f"(progress={progress.kind.value})."
            )
        if (
            progress.kind is ClarificationProgressKind.New
            and metadata is None
        ):
            raise ValueError(
                "Clarification answer did not affect its target distinction "
                "(progress=new)."
            )
        return PreparedClarificationTransition(
            successor, turn, progress, metadata=metadata
        )

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
    before_answer_fn: Callable[[ReasoningSession, ClarificationQuestion], None] | None = None,
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
        if before_answer_fn is not None:
            before_answer_fn(current, question)
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
    "TypedDeltaClarificationPolicy",
    "NONE_OF_THE_ABOVE_ANSWERS",
    "interactive_decision_profile",
    "run_interactive_dialogue",
]
