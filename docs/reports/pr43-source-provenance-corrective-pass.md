# PR #43 — source provenance corrective pass

This bounded corrective pass keeps the result of PR #43 unchanged:
the redacted PR #40 artifacts provide `insufficient_evidence`, not a semantic
error and not a verified receipt. No model-backed run was started, no
historical receipt was rewritten and no production admission path was changed.

## Source provenance

The normalization envelope contains the normalizer's `source_digest`, but a
normalizer assertion is not itself a host-selected source binding. The
evaluator now requires the host to pass `expected_source_digest`, obtained from
a trusted source manifest. The two digests use the same canonicalization:
UTF-8 text with CRLF normalized to LF before SHA-256.

The following distinction is intentional:

- a matching digest establishes that the normalizer named the host-selected
  source representation;
- it does not establish that the source material's commitments are true;
- the profile-relative basis still evaluates only the normalized commitments,
  and remains separate from a PR #41 adjudication receipt.

A missing, malformed or mismatched host digest fails closed as
`provenance=invalid`, `decision=not_comparable` and `usable=False`.

## Fail-closed boundaries

The public parser now reports mixed unknown top-level key types as a schema
error without sorting incomparable Python values and raising `TypeError`.
The JSON envelope itself is unchanged; this is only a defensive validation
fix for non-JSON `Mapping` callers.

The assessment regression derives the required public fields from each actual
PR #40 source artifact and verifies their absence. It therefore detects a
future artifact update that makes the stored `insufficient_evidence` result
stale instead of merely comparing the assessment with its own constants.

## Verification and scope

- full local suite: 535 passed;
- `compileall`: pass;
- `git diff --check`: pass;
- no new Bonsai/model-backed run;
- no synthetic normalization record or adjudication receipt;
- PRs #40–#42 unchanged;
- PR #43 remains Draft and is not merged.
