"""Typed clarification concepts and deterministic fixture policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Protocol

from .assessment import CandidateAssessment
from .candidates import FormalizationCandidate
from .cross_candidate import AssessmentLandscape, CrossCandidateStatus
from .interpretation import Ambiguity, InterpretationSpace


class ClarificationKind(str, Enum):
    Meaning = "Meaning"
    Ontology = "Ontology"
    Reference = "Reference"
    Presupposition = "Presupposition"
    Evidence = "Evidence"
    Perspective = "Perspective"
    Context = "Context"
    Formalization = "Formalization"


@dataclass(frozen=True)
class ClarificationQuestion:
    id: str
    kind: ClarificationKind
    text: str
    target_ids: tuple[str, ...]
    choices: tuple[str, ...] = ()
    # Host-owned semantic binding; replay must not infer it from wording.
    target_family: str | None = None
    # Runtime objects changed by a refinement.  ``target_ids`` above are
    # stable semantic references when grounding exists; these IDs remain
    # snapshot-local and are never used as semantic oracle identity.
    structural_target_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClarificationTurn:
    previous_interpretation_id: str
    question_id: str
    answer: str
    successor_interpretation_id: str


@dataclass(frozen=True)
class ClarificationState:
    turns: tuple[ClarificationTurn, ...] = ()

    def record(
        self,
        *,
        previous_interpretation_id: str,
        question_id: str,
        answer: str,
        successor_interpretation_id: str,
    ) -> "ClarificationState":
        if self.turns and previous_interpretation_id != self.turns[-1].successor_interpretation_id:
            raise ValueError(
                "Clarification history is discontinuous: expected previous "
                f"interpretation {self.turns[-1].successor_interpretation_id!r}, "
                f"got {previous_interpretation_id!r}."
            )
        return ClarificationState(
            turns=(
                *self.turns,
                ClarificationTurn(
                    previous_interpretation_id=previous_interpretation_id,
                    question_id=question_id,
                    answer=answer,
                    successor_interpretation_id=successor_interpretation_id,
                ),
            )
        )


@dataclass(frozen=True)
class ClarificationContext:
    interpretation: InterpretationSpace
    candidates: tuple[FormalizationCandidate, ...]
    assessments: tuple[CandidateAssessment, ...]
    landscape: AssessmentLandscape


def has_discriminating_reading_provenance(
    assessments: Iterable[CandidateAssessment],
) -> bool:
    """Return whether readings distinguish the competing formalizations.

    Every candidate must carry a reading, each formalization identity must map
    to exactly one reading, and the distinct formalization/readings sets must
    have the same cardinality. This deliberately rejects shared-reading
    conflicts instead of attributing them to the meaning axis.
    """

    collected = tuple(assessments)
    if not collected:
        return False
    readings_by_formalization: dict[str, set[str]] = {}
    for item in collected:
        reading_id = item.candidate.reading_id
        if reading_id is None:
            return False
        readings_by_formalization.setdefault(
            item.candidate.formalization_id, set()
        ).add(reading_id)
    if any(len(readings) != 1 for readings in readings_by_formalization.values()):
        return False
    formalization_ids = set(readings_by_formalization)
    reading_ids = {
        next(iter(readings)) for readings in readings_by_formalization.values()
    }
    return len(formalization_ids) > 1 and len(formalization_ids) == len(reading_ids)


class ClarificationPolicy(Protocol):
    def choose(self, context: ClarificationContext) -> ClarificationQuestion | None:
        ...


class KindAwareClarificationPolicy(ClarificationPolicy, Protocol):
    """Resolve a requested kind without inventing question provenance."""

    def choose_for_kind(
        self,
        context: ClarificationContext,
        kind: ClarificationKind,
    ) -> ClarificationQuestion | None:
        """Return a justified question of the requested kind, if one exists."""

        ...


class TransitionAwareClarificationPolicy(KindAwareClarificationPolicy, Protocol):
    """Apply an answer as an immutable interpretation transition."""

    def successor(
        self,
        *,
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
    ) -> tuple[InterpretationSpace, ClarificationTurn]:
        ...


@dataclass(frozen=True)
class FixtureClarificationPolicy:
    """Choose a provenance-aware question using deterministic rules."""

    transitions: Mapping[tuple[str, str, str], InterpretationSpace] = field(
        default_factory=dict
    )
    # Host-owned identity for model-produced semantic records.  Free-form
    # labels and positional IDs are not stable semantic target identity.
    semantic_target_families: Mapping[str, str] = field(default_factory=dict)
    semantic_target_kinds: Mapping[str, ClarificationKind] = field(default_factory=dict)
    require_semantic_target_families: bool = False

    def __post_init__(self) -> None:
        for target_id, target_family in self.semantic_target_families.items():
            if not isinstance(target_id, str) or not target_id.strip():
                raise ValueError("Semantic target binding ids must be non-empty strings.")
            if not isinstance(target_family, str) or not target_family.strip():
                raise ValueError("Semantic target binding families must be non-empty strings.")
        for target_id, kind in self.semantic_target_kinds.items():
            if not isinstance(target_id, str) or not target_id.strip():
                raise ValueError("Semantic target kind ids must be non-empty strings.")
            if kind not in {ClarificationKind.Meaning, ClarificationKind.Ontology}:
                raise ValueError("Semantic target kind must be Meaning or Ontology.")

    def _ambiguity_target_family(self, ambiguity: Ambiguity) -> str | None:
        # Only an explicit host-issued reference establishes grounding.  The
        # adapter's positional ``id`` is structural bookkeeping and must not
        # be treated as semantic identity.
        target_id = ambiguity.target_id
        if target_id in self.semantic_target_families:
            return self.semantic_target_families[target_id]
        if self.require_semantic_target_families:
            return None
        return ambiguity.term

    def _ambiguity_target_kind(self, ambiguity: Ambiguity) -> ClarificationKind:
        if ambiguity.target_id in self.semantic_target_kinds:
            return self.semantic_target_kinds[ambiguity.target_id]
        return ClarificationKind.Meaning

    @staticmethod
    def _question_targets(ambiguity: Ambiguity) -> tuple[str, ...]:
        return (ambiguity.target_id or ambiguity.id,)

    def questions(
        self, context: ClarificationContext
    ) -> tuple[ClarificationQuestion, ...]:
        """List deterministic questions justified by the supplied provenance."""

        interpretation = context.interpretation
        meaning_ambiguities = tuple(
            ambiguity
            for ambiguity in interpretation.ambiguities
            if self._ambiguity_target_kind(ambiguity) is ClarificationKind.Meaning
        )
        if meaning_ambiguities:
            return tuple(
                ClarificationQuestion(
                    id=f"meaning:{ambiguity.target_id or ambiguity.id}",
                    kind=ClarificationKind.Meaning,
                    text=f"Что именно означает «{ambiguity.term}» в этом вопросе?",
                    target_ids=self._question_targets(ambiguity),
                    target_family=self._ambiguity_target_family(ambiguity),
                    structural_target_ids=(ambiguity.id,),
                )
                for ambiguity in meaning_ambiguities
            )

        grounded_ontologies = tuple(
            ontology
            for ontology in interpretation.ontologies
            if ontology.target_id is not None
            and self.semantic_target_kinds.get(ontology.target_id)
            is ClarificationKind.Ontology
        )
        if grounded_ontologies:
            return tuple(
                ClarificationQuestion(
                    id=f"ontology:{ontology.target_id}",
                    kind=ClarificationKind.Ontology,
                    text="Какие онтологические допущения следует использовать?",
                    target_ids=(ontology.target_id,),
                    target_family=self.semantic_target_families.get(
                        ontology.target_id
                    ),
                    structural_target_ids=(ontology.id,),
                )
                for ontology in grounded_ontologies
            )

        landscape = context.landscape
        if landscape.status is CrossCandidateStatus.FormalizationUnresolved:
            unresolved = tuple(
                item
                for item in context.assessments
                if item.candidate.id in landscape.unresolved_candidate_ids
            )
            diagnostic_codes = {
                diagnostic.code
                for item in unresolved
                for diagnostic in item.result.diagnostics
            }
            question_specs = (
                (
                    "unknown_symbol",
                    ClarificationKind.Reference,
                    "Какой объект или референс имеется в виду?",
                ),
                (
                    "unknown_predicate",
                    ClarificationKind.Meaning,
                    "Как следует понимать этот предикат или термин?",
                ),
                (
                    "ontology_unresolved",
                    ClarificationKind.Ontology,
                    "Какие онтологические допущения следует использовать?",
                ),
                (
                    "presupposition_unresolved",
                    ClarificationKind.Presupposition,
                    "Какую предпосылку следует принять или отвергнуть?",
                ),
            )
            questions = tuple(
                ClarificationQuestion(
                    id=(
                        f"unresolved:{kind.value.lower()}:"
                        f"{','.join(landscape.unresolved_candidate_ids)}"
                    ),
                    kind=kind,
                    text=text,
                    target_ids=landscape.unresolved_candidate_ids,
                    target_family=(
                        None if self.require_semantic_target_families else "candidate"
                    ),
                    structural_target_ids=landscape.unresolved_candidate_ids,
                )
                for code, kind, text in question_specs
                if code in diagnostic_codes
            )
            if questions:
                return questions
            return (
                ClarificationQuestion(
                    id=f"unresolved:{','.join(landscape.unresolved_candidate_ids)}",
                    kind=ClarificationKind.Formalization,
                    text="Что нужно уточнить, чтобы завершить формализацию этого чтения?",
                    target_ids=landscape.unresolved_candidate_ids,
                    target_family="candidate",
                ),
            )

        if landscape.status is CrossCandidateStatus.ContextDependent:
            contexts = tuple(dict.fromkeys(item.context_id for item in context.assessments))
            return (
                ClarificationQuestion(
                    id="context:disambiguate",
                    kind=ClarificationKind.Context,
                    text="Какой из представленных контекстов следует использовать для оценки?",
                    target_ids=contexts,
                    choices=contexts,
                    target_family="context",
                ),
            )

        if landscape.status is CrossCandidateStatus.FormalizationConflict:
            reading_targets = tuple(
                dict.fromkeys(
                    item.candidate.reading_id
                    for item in context.assessments
                    if item.candidate.reading_id is not None
                )
            )
            if has_discriminating_reading_provenance(context.assessments):
                return (
                    ClarificationQuestion(
                        id="meaning:formalization",
                        kind=ClarificationKind.Meaning,
                        text="Какое смысловое чтение утверждения вы имеете в виду?",
                        target_ids=reading_targets,
                        choices=reading_targets,
                        target_family="reading",
                    ),
                )
            targets = tuple(item.candidate.id for item in context.assessments)
            return (
                ClarificationQuestion(
                    id="formalization:disambiguate",
                    kind=ClarificationKind.Formalization,
                    text="Какой вариант формализации следует рассматривать?",
                    target_ids=targets,
                    choices=targets,
                    target_family="candidate",
                ),
            )

        if landscape.status is CrossCandidateStatus.MixedDependence:
            reading_targets = tuple(
                dict.fromkeys(
                    item.candidate.reading_id
                    for item in context.assessments
                    if item.candidate.reading_id is not None
                )
            )
            if has_discriminating_reading_provenance(context.assessments):
                return (
                    ClarificationQuestion(
                        id="mixed:meaning",
                        kind=ClarificationKind.Meaning,
                        text="Какое смысловое чтение утверждения вы имеете в виду?",
                        target_ids=reading_targets,
                        choices=reading_targets,
                        target_family="reading",
                    ),
                )
            targets = tuple(dict.fromkeys(item.candidate.id for item in context.assessments))
            return (
                ClarificationQuestion(
                    id="mixed:formalization",
                    kind=ClarificationKind.Formalization,
                    text="Какой вариант формализации следует рассматривать?",
                    target_ids=targets,
                    choices=targets,
                    target_family="candidate",
                ),
            )

        return ()

    def choose(self, context: ClarificationContext) -> ClarificationQuestion | None:
        questions = self.questions(context)
        return questions[0] if questions else None

    def choose_for_kind(
        self,
        context: ClarificationContext,
        kind: ClarificationKind,
    ) -> ClarificationQuestion | None:
        return next(
            (question for question in self.questions(context) if question.kind is kind),
            None,
        )

    def successor(
        self,
        *,
        interpretation: InterpretationSpace,
        question: ClarificationQuestion,
        answer: str,
    ) -> tuple[InterpretationSpace, ClarificationTurn]:
        key = (interpretation.id, question.id, answer)
        try:
            successor = self.transitions[key]
        except KeyError as exc:
            raise KeyError(f"No clarification fixture transition for {key!r}.") from exc
        return successor, ClarificationTurn(
            previous_interpretation_id=interpretation.id,
            question_id=question.id,
            answer=answer,
            successor_interpretation_id=successor.id,
        )
