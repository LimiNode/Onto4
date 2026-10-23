# Source-backed semantic adjudication experiment

This research-only design is the next step after PR #43. It addresses one
operational gap: an independent normalizer must be able to show that its
`source_digest` refers to a particular host-selected source representation,
without publishing private model output or treating the digest as semantic
truth.

## Trusted source manifest

The host creates a `SourceManifest` for the exact source representation that
the normalizer is permitted to inspect. The manifest records:

- a host manifest ID and version;
- a source ID and source kind;
- the source digest and canonicalization identifier
  `utf8-lf-sha256-v1`;
- the previous/current snapshot IDs and host question ID;
- a host access attestation.

The manifest is host-side custody metadata. It is not included in provider
input, and it does not assert that the source has a particular meaning.

`evaluate_source_manifest` checks the complete canonical manifest digest
against a host-owned registry, the normalized record's digest and the
host-issued transition. The normalized record's snapshot IDs, question ID and
target must also match that transition; a digest cannot be reused to smuggle
evidence from another transition. A missing attestation, untrusted manifest
content, digest mismatch or transition mismatch fails closed. The evaluator
returns provenance/custody/transition statuses only; it does not produce a
semantic decision or an adjudication receipt.

The canonical source digest is computed by the shared helper over UTF-8 text
after CRLF is normalized to LF. Golden vectors cover LF, CRLF and Unicode. The
source representation must be preserved in the trusted contour long enough
for the host to reproduce that digest independently. A digest copied from a
normalizer without that host-owned manifest is not source-backed provenance.

## Future bounded run

The next experiment may use one of the frozen PR #40 cases, but it must first
create the manifest before normalization. The host then checks:

1. structural binding and transition provenance from PR #40;
2. source manifest custody and digest binding from this protocol;
3. independent normalizer identity and origin from PR #43;
4. profile-relative commitments from PR #42;
5. a separately reviewed decision about whether any result may become a PR
   #41 adjudication receipt.

The stages remain separate. A source manifest proves which source was
inspected, not that the source is semantically correct. Normalized commitments
remain profile-relative, and a successful deterministic contract does not
retroactively verify the historical Bonsai outputs.

No model-backed run, private-source import, synthetic receipt or production
admission change is part of this design PR.
