"""Protocol and deterministic fixtures for independent semantic evaluation.

This module defines the questions, labels and bounded corpus used by later
research-only annotation tools.  The fixtures are development references, not
independent semantic gold and never create production admission decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from typing import Any


PROTOCOL_VERSION = "pr61-semantic-evaluation-protocol-v1"
CORPUS_VERSION = "pr61-corpus-v1"


class TargetAlignment(str, Enum):
    ALIGNED = "aligned"
    MISALIGNED = "misaligned"
    INDETERMINATE = "indeterminate"


class AmbiguityResolution(str, Enum):
    RESOLVED = "resolved"
    NOT_RESOLVED = "not_resolved"
    MERELY_OMITTED = "merely_omitted"
    INDETERMINATE = "indeterminate"


class EvidenceSufficiency(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    CONTRADICTORY = "contradictory"
    NOT_AVAILABLE = "not_available"


class CaseClass(str, Enum):
    SAME_SEMANTICS_SAME_ID = "same_semantics_same_id"
    SAME_SEMANTICS_DIFFERENT_ID = "same_semantics_different_id"
    WRONG_SEMANTICS_CORRECT_ID = "wrong_semantics_correct_id"
    WRONG_SEMANTICS_DIFFERENT_ID = "wrong_semantics_different_id"
    GENUINELY_RESOLVED_AMBIGUITY = "genuinely_resolved_ambiguity"
    MERELY_OMITTED_AMBIGUITY = "merely_omitted_ambiguity"
    UNRELATED_VALID_REFINEMENT = "unrelated_valid_refinement"
    PARTIAL_CLARIFICATION = "partial_clarification"
    UNSUPPORTED_ONTOLOGICAL_ASSERTION = "unsupported_ontological_assertion"
    AMBIGUOUS_UNDECIDABLE_SUCCESSOR = "ambiguous_undecidable_successor"
    CONTRADICTORY_INTERPRETATION = "contradictory_interpretation"
    STRUCTURALLY_CHANGED_EQUIVALENT = "structurally_changed_equivalent"


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    family: str
    case_class: CaseClass
    initial_interpretation: str
    clarification_question: str
    intended_target_key: str
    intended_target_id: str
    proposed_successor: str
    expected_alignment: TargetAlignment
    expected_resolution: AmbiguityResolution
    expected_evidence: EvidenceSufficiency
    holdout: bool = False


def _case(
    case_id: str,
    family: str,
    case_class: CaseClass,
    initial: str,
    question: str,
    target_key: str,
    target_id: str,
    successor: str,
    alignment: TargetAlignment,
    resolution: AmbiguityResolution,
    evidence: EvidenceSufficiency,
    *,
    holdout: bool = False,
) -> EvaluationCase:
    return EvaluationCase(
        case_id,
        family,
        case_class,
        initial,
        question,
        target_key,
        target_id,
        successor,
        alignment,
        resolution,
        evidence,
        holdout,
    )


def corpus() -> tuple[EvaluationCase, ...]:
    """Return the frozen 16-case development/holdout fixture corpus."""

    genome_target = "genome_numerical_identity"
    time_target = "intrinsic_present"
    return (
        _case(
            "genome-dev-01", "genome_identity", CaseClass.SAME_SEMANTICS_SAME_ID,
            "Two organisms share a complete genome; the claim concerns numerical identity.",
            "Does the clarification concern numerical identity rather than similarity?",
            genome_target, "genome-target-01",
            "The organisms are numerically distinct despite sharing a genome.",
            TargetAlignment.ALIGNED, AmbiguityResolution.RESOLVED, EvidenceSufficiency.SUFFICIENT,
        ),
        _case(
            "genome-dev-02", "genome_identity", CaseClass.SAME_SEMANTICS_DIFFERENT_ID,
            "A shared genome is used to ask whether two organisms are one object.",
            "Is the target the numerical-identity question, not genetic resemblance?",
            genome_target, "genome-target-02",
            "The organisms remain distinct objects; shared genome does not entail identity.",
            TargetAlignment.ALIGNED, AmbiguityResolution.RESOLVED, EvidenceSufficiency.SUFFICIENT,
        ),
        _case(
            "genome-dev-03", "genome_identity", CaseClass.WRONG_SEMANTICS_CORRECT_ID,
            "The shared genome raises a question about numerical identity.",
            "Which target is being clarified: numerical identity or causal ancestry?",
            genome_target, "genome-target-03",
            "The organisms have a common ancestor, so the question is only about ancestry.",
            TargetAlignment.MISALIGNED, AmbiguityResolution.NOT_RESOLVED, EvidenceSufficiency.SUFFICIENT,
        ),
        _case(
            "genome-dev-04", "genome_identity", CaseClass.WRONG_SEMANTICS_DIFFERENT_ID,
            "The question asks whether shared genome makes organisms one individual.",
            "Does the refinement preserve the numerical-identity target?",
            genome_target, "genome-target-04",
            "The organisms are genetically similar and therefore belong to one species.",
            TargetAlignment.MISALIGNED, AmbiguityResolution.NOT_RESOLVED, EvidenceSufficiency.SUFFICIENT,
        ),
        _case(
            "genome-dev-05", "genome_identity", CaseClass.GENUINELY_RESOLVED_AMBIGUITY,
            "The phrase 'same genome' leaves identity and similarity readings open.",
            "Choose the reading that treats identity as a relation between distinct organisms.",
            genome_target, "genome-target-05",
            "The successor explicitly distinguishes numerical identity from genetic similarity.",
            TargetAlignment.ALIGNED, AmbiguityResolution.RESOLVED, EvidenceSufficiency.SUFFICIENT,
        ),
        _case(
            "genome-dev-06", "genome_identity", CaseClass.MERELY_OMITTED_AMBIGUITY,
            "The phrase 'same genome' leaves identity and similarity readings open.",
            "Choose the intended reading of 'same'.",
            genome_target, "genome-target-06",
            "The successor repeats that the organisms have the same genome.",
            TargetAlignment.ALIGNED, AmbiguityResolution.MERELY_OMITTED, EvidenceSufficiency.INSUFFICIENT,
        ),
        _case(
            "genome-dev-07", "genome_identity", CaseClass.UNRELATED_VALID_REFINEMENT,
            "The question concerns whether shared genome entails numerical identity.",
            "Clarify the identity relation at issue.",
            genome_target, "genome-target-07",
            "The organisms have different diets and habitats.",
            TargetAlignment.MISALIGNED, AmbiguityResolution.NOT_RESOLVED, EvidenceSufficiency.SUFFICIENT,
        ),
        _case(
            "time-dev-01", "intrinsic_time", CaseClass.PARTIAL_CLARIFICATION,
            "The claim says a sequence has an intrinsic present independent of observers.",
            "Is 'present' intrinsic to the sequence rather than an observer's coordinate?",
            time_target, "time-target-01",
            "The sequence has a present, but the relation to observer-independent time is not stated.",
            TargetAlignment.ALIGNED, AmbiguityResolution.NOT_RESOLVED, EvidenceSufficiency.INSUFFICIENT,
        ),
        _case(
            "time-dev-02", "intrinsic_time", CaseClass.UNSUPPORTED_ONTOLOGICAL_ASSERTION,
            "The claim asks whether a sequence has an intrinsic present.",
            "Does the refinement preserve the distinction between sequence order and intrinsic time?",
            time_target, "time-target-02",
            "A universal observer outside the system fixes the one true present.",
            TargetAlignment.MISALIGNED, AmbiguityResolution.NOT_RESOLVED, EvidenceSufficiency.INSUFFICIENT,
        ),
        _case(
            "time-dev-03", "intrinsic_time", CaseClass.AMBIGUOUS_UNDECIDABLE_SUCCESSOR,
            "The sequence's intrinsic present is contrasted with observer time.",
            "Which temporal notion is being asserted by the successor?",
            time_target, "time-target-03",
            "The present is real in some sense, while the sequence is ordered somehow.",
            TargetAlignment.INDETERMINATE, AmbiguityResolution.INDETERMINATE, EvidenceSufficiency.NOT_AVAILABLE,
        ),
        _case(
            "time-dev-04", "intrinsic_time", CaseClass.CONTRADICTORY_INTERPRETATION,
            "The claim distinguishes intrinsic present from an observer's coordinate time.",
            "Does the successor keep those two temporal notions distinct?",
            time_target, "time-target-04",
            "There is no intrinsic present, and the intrinsic present is the sequence's real time.",
            TargetAlignment.INDETERMINATE, AmbiguityResolution.INDETERMINATE, EvidenceSufficiency.CONTRADICTORY,
        ),
        _case(
            "time-dev-05", "intrinsic_time", CaseClass.STRUCTURALLY_CHANGED_EQUIVALENT,
            "A sequence may have an intrinsic present without importing observer time.",
            "Preserve the intrinsic/observer-time distinction while changing representation.",
            time_target, "time-target-05",
            "The representation changes from a timeline to indexed states, but intrinsic present remains the target.",
            TargetAlignment.ALIGNED, AmbiguityResolution.RESOLVED, EvidenceSufficiency.SUFFICIENT,
        ),
        _case(
            "time-holdout-01", "intrinsic_time", CaseClass.SAME_SEMANTICS_DIFFERENT_ID,
            "The sequence's present is claimed to be intrinsic rather than observer-relative.",
            "Does the successor preserve that intrinsic temporal target?",
            time_target, "time-holdout-01",
            "The sequence has an intrinsic present even though its technical identifier changes.",
            TargetAlignment.ALIGNED, AmbiguityResolution.RESOLVED, EvidenceSufficiency.SUFFICIENT,
            holdout=True,
        ),
        _case(
            "time-holdout-02", "intrinsic_time", CaseClass.WRONG_SEMANTICS_CORRECT_ID,
            "The claim is about intrinsic present, not an observer's coordinate time.",
            "Which temporal target does the successor preserve?",
            time_target, "time-holdout-02",
            "The observer's clock supplies the only meaning of present.",
            TargetAlignment.MISALIGNED, AmbiguityResolution.NOT_RESOLVED, EvidenceSufficiency.SUFFICIENT,
            holdout=True,
        ),
        _case(
            "genome-holdout-01", "genome_identity", CaseClass.MERELY_OMITTED_AMBIGUITY,
            "Shared genome can mean identity or only similarity.",
            "Which meaning of 'same' is intended?",
            genome_target, "genome-holdout-01",
            "The successor says only that the genome is shared.",
            TargetAlignment.ALIGNED, AmbiguityResolution.MERELY_OMITTED, EvidenceSufficiency.INSUFFICIENT,
            holdout=True,
        ),
        _case(
            "genome-holdout-02", "genome_identity", CaseClass.AMBIGUOUS_UNDECIDABLE_SUCCESSOR,
            "The question concerns numerical identity under genome sharing.",
            "Does the successor settle identity rather than similarity?",
            genome_target, "genome-holdout-02",
            "The organisms are one and not one depending on the relevant sense.",
            TargetAlignment.INDETERMINATE, AmbiguityResolution.INDETERMINATE, EvidenceSufficiency.NOT_AVAILABLE,
            holdout=True,
        ),
    )


def validate_case(case: EvaluationCase) -> None:
    required = {
        "case_id": case.case_id,
        "family": case.family,
        "initial_interpretation": case.initial_interpretation,
        "clarification_question": case.clarification_question,
        "intended_target_key": case.intended_target_key,
        "intended_target_id": case.intended_target_id,
        "proposed_successor": case.proposed_successor,
    }
    if any(not value.strip() for value in required.values()):
        raise ValueError("evaluation case contains an empty required field")
    if not case.case_id.startswith(("genome-", "time-")):
        raise ValueError("evaluation case id must be scoped to a corpus family")
    if case.family not in {"genome_identity", "intrinsic_time"}:
        raise ValueError("unsupported evaluation family")


def canonical_case(case: EvaluationCase) -> dict[str, Any]:
    value = asdict(case)
    for key in ("case_class", "expected_alignment", "expected_resolution", "expected_evidence"):
        value[key] = value[key].value
    return value


def case_commitment(case: EvaluationCase) -> str:
    """Return a deterministic integrity digest, never a public gold label."""

    payload = {key: value for key, value in canonical_case(case).items() if key != "holdout"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def holdout_manifest() -> dict[str, Any]:
    cases = corpus()
    for case in cases:
        validate_case(case)
    holdout = [case for case in cases if case.holdout]
    return {
        "record_type": "pr61_frozen_holdout_manifest",
        "protocol_version": PROTOCOL_VERSION,
        "corpus_version": CORPUS_VERSION,
        "holdout_size": len(holdout),
        "holdout_case_aliases": [case.case_id for case in holdout],
        "commitments": [case_commitment(case) for case in holdout],
        "labels_published": False,
        "raw_text_published": False,
        "independent_gold_available": False,
    }


def protocol_artifact() -> dict[str, Any]:
    cases = corpus()
    for case in cases:
        validate_case(case)
    development = [case for case in cases if not case.holdout]
    return {
        "record_type": "pr61_semantic_evaluation_protocol",
        "protocol_version": PROTOCOL_VERSION,
        "corpus_version": CORPUS_VERSION,
        "case_count": len(cases),
        "development_count": len(development),
        "holdout_count": len(cases) - len(development),
        "families": sorted({case.family for case in cases}),
        "case_classes": sorted({case.case_class.value for case in cases}),
        "independent_gold_available": False,
        "real_model_calls": False,
        "production_authority_changed": False,
        "holdout_manifest": holdout_manifest(),
    }
