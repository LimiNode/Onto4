"""Host-owned source manifests for a future source-backed experiment.

The manifest is custody and provenance metadata, not semantic evidence.  It
names the exact source representation that an independent normalizer was
allowed to inspect.  The manifest is supplied by the host; it is never a
provider-facing field and it cannot create an adjudication receipt.
"""

from __future__ import annotations

import re
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .semantic_binding import BindingRelation, BindingTransition, CheckStatus
from .semantic_normalization import IndependentEvidenceNormalization


class SourceManifestSchemaError(ValueError):
    """A host-owned source manifest has an invalid envelope."""


_SHA256 = re.compile(r"[0-9a-f]{64}")
_CANONICALIZATION = "utf8-lf-sha256-v1"


def canonical_source_digest(source_text: str) -> str:
    """Return the canonical digest for host-selected textual source bytes."""

    if not isinstance(source_text, str):
        raise TypeError("Canonical source digest input must be text.")
    canonical = source_text.replace("\r\n", "\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class SourceManifest:
    """Host-owned description of one source representation."""

    manifest_id: str
    version: str
    source_id: str
    source_kind: str
    source_digest: str
    canonicalization: str
    previous_snapshot_id: str
    current_snapshot_id: str
    question_id: str
    access_attested: bool

    @property
    def manifest_digest(self) -> str:
        """Digest the complete manifest content for the host registry."""

        payload = {
            "manifest_id": self.manifest_id,
            "version": self.version,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "source_digest": self.source_digest,
            "canonicalization": self.canonicalization,
            "previous_snapshot_id": self.previous_snapshot_id,
            "current_snapshot_id": self.current_snapshot_id,
            "question_id": self.question_id,
            "access_attested": self.access_attested,
        }
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class SourceManifestEvaluation:
    """Custody/provenance checks, intentionally without a semantic decision."""

    manifest: SourceManifest | None
    schema: CheckStatus
    provenance: CheckStatus
    custody: CheckStatus
    transition: CheckStatus
    errors: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return all(
            status is CheckStatus.VALID
            for status in (self.schema, self.provenance, self.custody, self.transition)
        )


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SourceManifestSchemaError(
            f"Source manifest field {field!r} must be a non-empty string."
        )
    return value


def _typed_manifest_errors(manifest: SourceManifest) -> tuple[str, ...]:
    errors: list[str] = []
    for field in (
        "manifest_id",
        "version",
        "source_id",
        "source_kind",
        "source_digest",
        "canonicalization",
        "previous_snapshot_id",
        "current_snapshot_id",
        "question_id",
    ):
        value = getattr(manifest, field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Source manifest field {field!r} must be a non-empty string.")
    if isinstance(manifest.source_digest, str) and _SHA256.fullmatch(manifest.source_digest) is None:
        errors.append("Source manifest source_digest must be a lowercase SHA-256 digest.")
    if manifest.canonicalization != _CANONICALIZATION:
        errors.append(
            f"Unsupported source manifest canonicalization: {manifest.canonicalization!r}."
        )
    if not isinstance(manifest.access_attested, bool):
        errors.append("Source manifest access_attested must be boolean.")
    return tuple(errors)


def parse_source_manifest(payload: Mapping[str, Any]) -> SourceManifest:
    """Parse an exact host-side manifest envelope."""

    if not isinstance(payload, Mapping):
        raise SourceManifestSchemaError("Source manifest must be an object.")
    required = {
        "manifest_id",
        "version",
        "source_id",
        "source_kind",
        "source_digest",
        "canonicalization",
        "previous_snapshot_id",
        "current_snapshot_id",
        "question_id",
        "access_attested",
    }
    unknown = [key for key in payload if key not in required]
    missing = required - set(payload)
    if unknown:
        raise SourceManifestSchemaError(f"Unknown source manifest fields: {unknown!r}.")
    if missing:
        raise SourceManifestSchemaError(f"Missing source manifest fields: {sorted(missing)!r}.")
    manifest = SourceManifest(
        manifest_id=_required_string(payload, "manifest_id"),
        version=_required_string(payload, "version"),
        source_id=_required_string(payload, "source_id"),
        source_kind=_required_string(payload, "source_kind"),
        source_digest=payload["source_digest"],
        canonicalization=payload["canonicalization"],
        previous_snapshot_id=_required_string(payload, "previous_snapshot_id"),
        current_snapshot_id=_required_string(payload, "current_snapshot_id"),
        question_id=_required_string(payload, "question_id"),
        access_attested=payload["access_attested"],
    )
    errors = _typed_manifest_errors(manifest)
    if errors:
        raise SourceManifestSchemaError(errors[0])
    return manifest


def _normalization_errors(
    normalization: IndependentEvidenceNormalization,
) -> tuple[str, ...]:
    errors: list[str] = []
    for field in (
        "case_id",
        "previous_snapshot_id",
        "current_snapshot_id",
        "target_id",
        "question_id",
        "basis_digest",
        "normalizer_id",
        "normalizer_version",
        "source_digest",
    ):
        value = getattr(normalization, field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Normalization field {field!r} must be a non-empty string.")
    if not isinstance(normalization.relation, BindingRelation):
        errors.append("Normalization relation must be a BindingRelation.")
    answer_ids = normalization.answer_ids
    if (
        not isinstance(answer_ids, tuple)
        or not answer_ids
        or any(not isinstance(item, str) or not item.strip() for item in answer_ids)
        or len(set(answer_ids)) != len(answer_ids)
    ):
        errors.append("Normalization answer_ids must be a unique non-empty tuple of strings.")
    if not isinstance(normalization.commitments, Mapping):
        errors.append("Normalization commitments must be a mapping.")
    if isinstance(normalization.source_digest, str) and _SHA256.fullmatch(normalization.source_digest) is None:
        errors.append("Normalization source_digest must be a lowercase SHA-256 digest.")
    return tuple(errors)


def evaluate_source_manifest(
    manifest: SourceManifest | Mapping[str, Any],
    *,
    normalization: IndependentEvidenceNormalization,
    transition: BindingTransition,
    trusted_manifest_registry: Mapping[str, str],
) -> SourceManifestEvaluation:
    """Check that a normalized record used a host-selected source manifest."""

    if isinstance(manifest, Mapping):
        try:
            manifest = parse_source_manifest(manifest)
        except SourceManifestSchemaError as exc:
            return SourceManifestEvaluation(
                manifest=None,
                schema=CheckStatus.INVALID,
                provenance=CheckStatus.NOT_APPLICABLE,
                custody=CheckStatus.NOT_APPLICABLE,
                transition=CheckStatus.NOT_APPLICABLE,
                errors=(str(exc),),
            )
    if not isinstance(manifest, SourceManifest):
        return SourceManifestEvaluation(
            manifest=None,
            schema=CheckStatus.INVALID,
            provenance=CheckStatus.NOT_APPLICABLE,
            custody=CheckStatus.NOT_APPLICABLE,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=("Source manifest has an unsupported host-side type.",),
        )
    manifest_errors = _typed_manifest_errors(manifest)
    if manifest_errors:
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.INVALID,
            provenance=CheckStatus.NOT_APPLICABLE,
            custody=CheckStatus.NOT_APPLICABLE,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=manifest_errors,
        )
    if not isinstance(normalization, IndependentEvidenceNormalization):
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.INVALID,
            provenance=CheckStatus.NOT_APPLICABLE,
            custody=CheckStatus.NOT_APPLICABLE,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=("Normalization has an unsupported host-side type.",),
        )
    normalization_errors = _normalization_errors(normalization)
    if normalization_errors:
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.INVALID,
            provenance=CheckStatus.NOT_APPLICABLE,
            custody=CheckStatus.NOT_APPLICABLE,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=normalization_errors,
        )
    trusted_manifest_digest = trusted_manifest_registry.get(manifest.manifest_id)
    if trusted_manifest_digest != manifest.manifest_digest:
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.INVALID,
            custody=CheckStatus.NOT_APPLICABLE,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=("Source manifest content is not trusted by the host.",),
        )
    if manifest.source_digest != normalization.source_digest:
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.INVALID,
            custody=CheckStatus.NOT_APPLICABLE,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=("Source manifest digest does not match normalized evidence.",),
        )
    if not manifest.access_attested:
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.VALID,
            custody=CheckStatus.INVALID,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=("Host source access attestation is required.",),
        )
    if (
        manifest.previous_snapshot_id != transition.previous.id
        or manifest.current_snapshot_id != transition.current.id
        or manifest.question_id != transition.question.id
    ):
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.VALID,
            custody=CheckStatus.VALID,
            transition=CheckStatus.INVALID,
            errors=("Source manifest does not match the host transition.",),
        )
    if (
        normalization.previous_snapshot_id != transition.previous.id
        or normalization.current_snapshot_id != transition.current.id
        or normalization.question_id != transition.question.id
        or normalization.target_id not in transition.question.target_ids
    ):
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.VALID,
            custody=CheckStatus.VALID,
            transition=CheckStatus.INVALID,
            errors=("Normalized evidence does not match the host transition or question target.",),
        )
    return SourceManifestEvaluation(
        manifest=manifest,
        schema=CheckStatus.VALID,
        provenance=CheckStatus.VALID,
        custody=CheckStatus.VALID,
        transition=CheckStatus.VALID,
    )


__all__ = [
    "SourceManifest",
    "SourceManifestEvaluation",
    "SourceManifestSchemaError",
    "canonical_source_digest",
    "evaluate_source_manifest",
    "parse_source_manifest",
]
