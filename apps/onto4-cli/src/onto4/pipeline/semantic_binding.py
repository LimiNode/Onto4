"""Research-only validation for host-controlled semantic target binding.

The protocol deliberately keeps four structural checks independent from the
semantic claim made by a provider.  A valid public id proves only that the
provider referred to a known host target; it does not prove that the returned
text preserves the target's meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from onto4.reasoning import ClarificationKind, ClarificationQuestion, InterpretationSpace


class BindingSchemaError(ValueError):
    """A provider binding claim cannot be parsed as the protocol schema."""


class BindingRelation(str, Enum):
    PRESERVE = "preserve"
    ANCHORED_UPDATE = "anchored_update"
    CREATE = "create"
    NO_BINDING = "no_binding"


class CheckStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


class SemanticIdentityStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True)
class PublicSemanticTarget:
    """A host-owned public target descriptor.

    ``description`` is explanatory metadata only.  It is never used as a
    semantic oracle for a provider's returned text.
    """

    id: str
    kind: str
    description: str = ""

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Semantic target id must not be empty.")
        if self.kind not in {ClarificationKind.Meaning.value, ClarificationKind.Ontology.value}:
            raise ValueError("Semantic target kind must be Meaning or Ontology.")


@dataclass(frozen=True)
class SemanticTargetCatalog:
    """Versioned host catalog used only for structural admission checks."""

    version: int
    targets: Mapping[str, PublicSemanticTarget]

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("Semantic target catalog version must be positive.")
        if not self.targets:
            raise ValueError("Semantic target catalog must not be empty.")
        if set(self.targets) != {target.id for target in self.targets.values()}:
            raise ValueError("Semantic target catalog keys must match target ids.")


@dataclass(frozen=True)
class BindingTransition:
    """One host-owned transition and the question that authorized it."""

    previous: InterpretationSpace
    current: InterpretationSpace
    question: ClarificationQuestion

    def __post_init__(self) -> None:
        if self.previous.id == self.current.id:
            raise ValueError("A binding transition requires distinct snapshots.")


@dataclass(frozen=True)
class BindingClaim:
    """Provider-supplied claim, parsed without granting it authority."""

    relation: BindingRelation
    target_id: str | None
    target_kind: str | None
    previous_snapshot_id: str
    current_snapshot_id: str
    source_target_id: str | None = None


@dataclass(frozen=True)
class BindingEvaluation:
    """Independent evidence for one binding claim."""

    claim: BindingClaim | None
    schema: CheckStatus
    catalog: CheckStatus
    lineage: CheckStatus
    transition: CheckStatus
    semantic_identity: SemanticIdentityStatus
    errors: tuple[str, ...] = ()
    evaluated_previous_snapshot_id: str | None = None
    evaluated_current_snapshot_id: str | None = None
    evaluated_question_id: str | None = None

    @property
    def structurally_admissible(self) -> bool:
        return self.claim is not None and self.claim.relation is not BindingRelation.NO_BINDING and all(
            status is CheckStatus.VALID
            for status in (self.schema, self.catalog, self.lineage, self.transition)
        )


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BindingSchemaError(f"Binding claim field {field!r} must be a non-empty string.")
    return value


def parse_binding_claim(payload: Mapping[str, Any]) -> BindingClaim:
    """Parse a provider response; unknown fields are rejected fail-closed."""

    if not isinstance(payload, Mapping):
        raise BindingSchemaError("Binding claim must be an object.")
    allowed = {
        "relation",
        "target_id",
        "target_kind",
        "previous_snapshot_id",
        "current_snapshot_id",
        "source_target_id",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise BindingSchemaError(f"Unknown binding claim fields: {sorted(unknown)!r}.")
    try:
        relation = BindingRelation(_required_string(payload, "relation"))
    except ValueError as exc:
        raise BindingSchemaError("Binding claim relation is unsupported.") from exc
    previous = _required_string(payload, "previous_snapshot_id")
    current = _required_string(payload, "current_snapshot_id")
    target_id = payload.get("target_id")
    target_kind = payload.get("target_kind")
    source_target_id = payload.get("source_target_id")
    for field, value in (
        ("target_id", target_id),
        ("target_kind", target_kind),
        ("source_target_id", source_target_id),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise BindingSchemaError(f"Binding claim field {field!r} must be a non-empty string or null.")
    if relation is BindingRelation.NO_BINDING:
        if target_id is not None or target_kind is not None or source_target_id is not None:
            raise BindingSchemaError("A no_binding claim cannot carry a target.")
    elif target_id is None or target_kind is None:
        raise BindingSchemaError("A binding claim must include target_id and target_kind.")
    if relation is BindingRelation.PRESERVE and source_target_id is None:
        raise BindingSchemaError("A preserve claim requires source_target_id.")
    if relation is BindingRelation.ANCHORED_UPDATE and source_target_id is None:
        raise BindingSchemaError("An anchored_update claim requires source_target_id.")
    if relation is BindingRelation.CREATE and source_target_id is not None:
        raise BindingSchemaError("A create claim cannot carry source_target_id.")
    return BindingClaim(
        relation=relation,
        target_id=target_id,
        target_kind=target_kind,
        previous_snapshot_id=previous,
        current_snapshot_id=current,
        source_target_id=source_target_id,
    )


def _snapshot_targets(snapshot: InterpretationSpace) -> tuple[dict[str, str], tuple[str, ...]]:
    targets: dict[str, str] = {}
    errors: list[str] = []
    for ambiguity in snapshot.ambiguities:
        if ambiguity.target_id is not None:
            target_id = ambiguity.target_id
            kind = ClarificationKind.Meaning.value
            previous_kind = targets.get(target_id)
            if previous_kind is not None:
                errors.append(f"Snapshot contains duplicate target id {target_id!r}.")
                if previous_kind != kind:
                    errors.append(f"Snapshot contains conflicting kinds for target id {target_id!r}.")
            else:
                targets[target_id] = kind
    for ontology in snapshot.ontologies:
        if ontology.target_id is not None:
            target_id = ontology.target_id
            kind = ClarificationKind.Ontology.value
            previous_kind = targets.get(target_id)
            if previous_kind is not None:
                errors.append(f"Snapshot contains duplicate target id {target_id!r}.")
                if previous_kind != kind:
                    errors.append(f"Snapshot contains conflicting kinds for target id {target_id!r}.")
            else:
                targets[target_id] = kind
    return targets, tuple(errors)


def _snapshot_catalog_errors(
    snapshot_name: str,
    targets: Mapping[str, str],
    catalog: SemanticTargetCatalog,
) -> tuple[str, ...]:
    """Ensure every host snapshot target has its catalog-declared kind."""

    errors: list[str] = []
    for target_id, actual_kind in targets.items():
        public_target = catalog.targets.get(target_id)
        if public_target is None:
            errors.append(
                f"{snapshot_name} snapshot target id {target_id!r} is absent from the public catalog."
            )
        elif public_target.kind != actual_kind:
            errors.append(
                f"{snapshot_name} snapshot target {target_id!r} has kind {actual_kind!r}, "
                f"but the public catalog declares {public_target.kind!r}."
            )
    return tuple(errors)


def _invalid(
    claim: BindingClaim | None,
    *,
    schema: CheckStatus,
    catalog: CheckStatus,
    lineage: CheckStatus,
    transition: CheckStatus,
    errors: Sequence[str],
) -> BindingEvaluation:
    return BindingEvaluation(
        claim=claim,
        schema=schema,
        catalog=catalog,
        lineage=lineage,
        transition=transition,
        semantic_identity=SemanticIdentityStatus.UNVERIFIED,
        errors=tuple(errors),
    )


def evaluate_binding_claim(
    payload: Mapping[str, Any],
    *,
    transition: BindingTransition,
    catalog: SemanticTargetCatalog,
) -> BindingEvaluation:
    """Evaluate one claim without mutating or admitting a successor snapshot."""

    try:
        claim = parse_binding_claim(payload)
    except BindingSchemaError as exc:
        return _invalid(
            None,
            schema=CheckStatus.INVALID,
            catalog=CheckStatus.NOT_APPLICABLE,
            lineage=CheckStatus.NOT_APPLICABLE,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=(str(exc),),
        )

    errors: list[str] = []
    catalog_status = CheckStatus.VALID
    lineage_status = CheckStatus.VALID
    transition_status = CheckStatus.VALID

    if claim.relation is not BindingRelation.NO_BINDING:
        target = catalog.targets.get(claim.target_id or "")
        if target is None:
            catalog_status = CheckStatus.INVALID
            errors.append("Claim refers to an unknown target id.")
        elif target.kind != claim.target_kind:
            catalog_status = CheckStatus.INVALID
            errors.append("Claim target kind does not match the public catalog.")
        elif target.kind != transition.question.kind.value:
            catalog_status = CheckStatus.INVALID
            errors.append("Claim target kind does not match the issued question kind.")

    if (
        claim.previous_snapshot_id != transition.previous.id
        or claim.current_snapshot_id != transition.current.id
    ):
        lineage_status = CheckStatus.INVALID
        errors.append("Claim snapshot lineage does not match the host transition.")

    previous_targets, previous_snapshot_errors = _snapshot_targets(transition.previous)
    current_targets, current_snapshot_errors = _snapshot_targets(transition.current)
    snapshot_catalog_errors = (
        *_snapshot_catalog_errors("Previous", previous_targets, catalog),
        *_snapshot_catalog_errors("Current", current_targets, catalog),
    )
    snapshot_errors = (
        *previous_snapshot_errors,
        *current_snapshot_errors,
        *snapshot_catalog_errors,
    )
    if snapshot_errors:
        transition_status = CheckStatus.INVALID
        errors.extend(snapshot_errors)
    question_targets = set(transition.question.target_ids)
    if claim.relation is BindingRelation.NO_BINDING:
        if not snapshot_errors:
            transition_status = CheckStatus.VALID
    elif claim.target_id not in question_targets:
        transition_status = CheckStatus.INVALID
        errors.append("Claim target is not one of the host-issued question targets.")
    elif claim.relation is BindingRelation.PRESERVE:
        if claim.source_target_id != claim.target_id:
            transition_status = CheckStatus.INVALID
            errors.append("A preserve claim must retain the source target identity.")
        elif claim.target_id not in previous_targets or claim.target_id not in current_targets:
            transition_status = CheckStatus.INVALID
            errors.append("A preserve claim must bind the target in both snapshots.")
    elif claim.relation is BindingRelation.ANCHORED_UPDATE:
        if claim.source_target_id != claim.target_id:
            transition_status = CheckStatus.INVALID
            errors.append("An anchored update must retain the source target identity.")
        elif claim.target_id not in previous_targets or claim.target_id not in current_targets:
            transition_status = CheckStatus.INVALID
            errors.append("An anchored update must bind the target in both snapshots.")
    elif claim.relation is BindingRelation.CREATE:
        if claim.target_id not in current_targets or claim.target_id in previous_targets:
            transition_status = CheckStatus.INVALID
            errors.append("A create claim must introduce a target only in the current snapshot.")

    return BindingEvaluation(
        claim=claim,
        schema=CheckStatus.VALID,
        catalog=catalog_status,
        lineage=lineage_status,
        transition=transition_status,
        semantic_identity=(
            SemanticIdentityStatus.NOT_COMPARABLE
            if claim.relation is BindingRelation.NO_BINDING
            else SemanticIdentityStatus.UNVERIFIED
        ),
        errors=tuple(errors),
        evaluated_previous_snapshot_id=transition.previous.id,
        evaluated_current_snapshot_id=transition.current.id,
        evaluated_question_id=transition.question.id,
    )


def evaluate_binding_claims(
    payloads: Sequence[Mapping[str, Any]],
    *,
    transition: BindingTransition,
    catalog: SemanticTargetCatalog,
) -> tuple[BindingEvaluation, ...]:
    """Evaluate claims and reject duplicate/conflicting claims independently."""

    evaluations = list(
        evaluate_binding_claim(payload, transition=transition, catalog=catalog)
        for payload in payloads
    )
    seen: dict[tuple[str, str], int] = {}
    for index, evaluation in enumerate(evaluations):
        claim = evaluation.claim
        if claim is None or claim.target_id is None:
            continue
        key = (claim.target_id, claim.current_snapshot_id)
        previous = seen.get(key)
        if previous is not None:
            evaluations[index] = BindingEvaluation(
                claim=claim,
                schema=evaluation.schema,
                catalog=evaluation.catalog,
                lineage=evaluation.lineage,
                transition=CheckStatus.INVALID,
                semantic_identity=evaluation.semantic_identity,
                errors=(*evaluation.errors, "Duplicate or conflicting binding claim."),
                evaluated_previous_snapshot_id=evaluation.evaluated_previous_snapshot_id,
                evaluated_current_snapshot_id=evaluation.evaluated_current_snapshot_id,
                evaluated_question_id=evaluation.evaluated_question_id,
            )
            first = evaluations[previous]
            evaluations[previous] = BindingEvaluation(
                claim=first.claim,
                schema=first.schema,
                catalog=first.catalog,
                lineage=first.lineage,
                transition=CheckStatus.INVALID,
                semantic_identity=first.semantic_identity,
                errors=(*first.errors, "Duplicate or conflicting binding claim."),
                evaluated_previous_snapshot_id=first.evaluated_previous_snapshot_id,
                evaluated_current_snapshot_id=first.evaluated_current_snapshot_id,
                evaluated_question_id=first.evaluated_question_id,
            )
        else:
            seen[key] = index
    return tuple(evaluations)


__all__ = [
    "BindingClaim",
    "BindingEvaluation",
    "BindingRelation",
    "BindingSchemaError",
    "BindingTransition",
    "CheckStatus",
    "PublicSemanticTarget",
    "SemanticIdentityStatus",
    "SemanticTargetCatalog",
    "evaluate_binding_claim",
    "evaluate_binding_claims",
    "parse_binding_claim",
]
