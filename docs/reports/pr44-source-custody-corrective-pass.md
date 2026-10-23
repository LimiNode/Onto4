# PR #44 — source custody corrective pass

This bounded corrective pass keeps PR #44 design-only. It adds no private
source material, model-backed run, semantic receipt or production-admission
change.

## Corrected invariants

`evaluate_source_manifest` now checks the complete chain:

- the typed or parsed manifest satisfies the same schema invariants;
- the host registry contains the canonical digest of the complete manifest;
- the manifest digest matches the normalized evidence source digest;
- manifest and normalized evidence agree with the same previous/current
  snapshots and question;
- the normalized target belongs to the host-issued question;
- host access attestation is a real boolean and is true.

A digest match alone cannot reuse evidence from a different transition. A
manifest and a normalization record must jointly refer to the same host
transition. `usable=True` therefore means that the custody/provenance boundary
and these cross-object transition checks all passed; it is not a semantic
decision and does not create a PR #41 receipt.

The registry stores the host-selected complete manifest digest, rather than
only an ID/version pair. A caller-provided object with the same label but
different source content is rejected.

## Canonicalization

`canonical_source_digest` implements `utf8-lf-sha256-v1`: normalize CRLF to LF,
encode UTF-8, then compute SHA-256. Golden vectors cover LF, CRLF and Unicode.
No private model output is needed for these vectors.

## Verification

- full local suite: 547 passed;
- `compileall`: pass;
- `git diff --check`: pass;
- no model-backed run or private-source import;
- PRs #40–#43 unchanged;
- PR #44 remains Draft and is not merged.
