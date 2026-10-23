"""Normalize one frozen public corpus answer with a content-sensitive rubric.

This is a research-only, bounded normalizer for the first turn of
``genome-identity-bounded``.  It is intentionally a separate procedure from
the experiment runner: it reads the answer text and derives the one
profile-relevant commitment from explicit, documented discriminators.

It is not a general natural-language semantics engine and it is not a
universal Onto4 oracle.  Text outside the frozen discriminator set is left
``unspecified`` rather than guessed.
"""

from __future__ import annotations

from typing import Mapping

from onto4.pipeline import (
    GENOME_IDENTITY_FIRST_TURN_BASIS,
    IndependentEvidenceNormalization,
)


NORMALIZER_ID = "independent-corpus-rubric"
NORMALIZER_VERSION = "v3"
COMMITMENT_KEY = "identity_criterion_is_numerical"

# This intentionally accepts a small frozen grammar instead of matching
# keywords.  A phrase mentioning a criterion can affirm, reject, or contrast
# it; unfamiliar wording must remain unspecified rather than be guessed.
_AFFIRMED_ANSWERS = {
    "i mean numerical identity: they are one and the same individual.",
    "i mean numerical identity.",
    "i mean not genetic similarity, but numerical identity.",
}
_DENIED_ANSWERS = {
    "i reject numerical identity.",
    "i mean genetic similarity, not numerical identity.",
}


def _normalized_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("The corpus answer must be text.")
    return " ".join(value.split()).casefold()


def derive_identity_commitment(answer: str) -> str:
    """Derive the frozen basis commitment from the inspected answer text."""

    normalized = _normalized_text(answer)
    if normalized in _AFFIRMED_ANSWERS:
        return "affirmed"
    if normalized in _DENIED_ANSWERS:
        return "denied"
    return "unspecified"


def normalize_genome_identity_first_turn(
    source: Mapping[str, object], *, source_digest: str
) -> IndependentEvidenceNormalization:
    """Produce evidence from the actual public source slice, not a constant."""

    if source.get("case_id") != "genome-identity-bounded":
        raise ValueError("This normalizer only supports genome-identity-bounded.")
    if source.get("question_id") != "meaning:ambiguity-genome":
        raise ValueError("This normalizer only supports the frozen meaning question.")
    if source.get("target_id") != "ambiguity-genome":
        raise ValueError("This normalizer only supports the frozen genome target.")
    if source.get("selected_turn_ids") != ["genome-1", "genome-2"]:
        raise ValueError("This normalizer requires the frozen first-turn source slice.")

    return IndependentEvidenceNormalization(
        case_id="genome-identity-bounded",
        previous_snapshot_id="corpus:genome-1",
        current_snapshot_id="corpus:genome-2",
        target_id="ambiguity-genome",
        question_id="meaning:ambiguity-genome",
        answer_ids=("genome-2",),
        relation=GENOME_IDENTITY_FIRST_TURN_BASIS.relation,
        basis_digest=GENOME_IDENTITY_FIRST_TURN_BASIS.basis_digest,
        normalizer_id=NORMALIZER_ID,
        normalizer_version=NORMALIZER_VERSION,
        source_digest=source_digest,
        commitments={COMMITMENT_KEY: derive_identity_commitment(source.get("answer", ""))},
    )
