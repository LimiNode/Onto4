"""Host-owned source manifests for a future source-backed experiment.

The manifest is custody and provenance metadata, not semantic evidence.  It
names the exact source representation that an independent normalizer was
allowed to inspect.  The manifest is supplied by the host; it is never a
provider-facing field and it cannot create an adjudication receipt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .semantic_binding import BindingTransition, CheckStatus
from .semantic_normalization import IndependentEvidenceNormalization


class SourceManifestSchemaError(ValueError):
    """A host-owned source manifest has an invalid envelope."""


_SHA256 = re.compile(r"[0-9a-f]{64}")
_CANONICALIZATION = "utf8-lf-sha256-v1"


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
    digest = _required_string(payload, "source_digest")
    if _SHA256.fullmatch(digest) is None:
        raise SourceManifestSchemaError(
            "Source manifest source_digest must be a lowercase SHA-256 digest."
        )
    if payload["canonicalization"] != _CANONICALIZATION:
        raise SourceManifestSchemaError(
            f"Unsupported source manifest canonicalization: {payload['canonicalization']!r}."
        )
    if not isinstance(payload["access_attested"], bool):
        raise SourceManifestSchemaError("Source manifest access_attested must be boolean.")
    return SourceManifest(
        manifest_id=_required_string(payload, "manifest_id"),
        version=_required_string(payload, "version"),
        source_id=_required_string(payload, "source_id"),
        source_kind=_required_string(payload, "source_kind"),
        source_digest=digest,
        canonicalization=_CANONICALIZATION,
        previous_snapshot_id=_required_string(payload, "previous_snapshot_id"),
        current_snapshot_id=_required_string(payload, "current_snapshot_id"),
        question_id=_required_string(payload, "question_id"),
        access_attested=payload["access_attested"],
    )


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
    if trusted_manifest_registry.get(manifest.manifest_id) != manifest.version:
        return SourceManifestEvaluation(
            manifest=manifest,
            schema=CheckStatus.VALID,
            provenance=CheckStatus.INVALID,
            custody=CheckStatus.NOT_APPLICABLE,
            transition=CheckStatus.NOT_APPLICABLE,
            errors=("Source manifest identity or version is not trusted by the host.",),
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
    "evaluate_source_manifest",
    "parse_source_manifest",
]
