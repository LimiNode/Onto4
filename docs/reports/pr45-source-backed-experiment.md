# PR #45 — bounded source-backed experiment

This research-only experiment runs one frozen case against an exact,
host-selected slice of the public `bounded-dialogue-v1` corpus. The source is
the first turn of `genome-identity-bounded`: question `genome-1` and answer
`genome-2`. It is a reproducible source fixture, not a recovered successor
snapshot from the historical PR #40 provider run.

## What the experiment establishes

The host canonicalizes the selected source representation with
`utf8-lf-sha256-v1` and records its digest in a `SourceManifest`. The manifest
binds the source to the host transition (`corpus:genome-1` →
`corpus:genome-2`) and the question `meaning:ambiguity-genome`.

The independent normalizer then commits to the profile-relative
`GENOME_IDENTITY_FIRST_TURN_BASIS`, including the commitment that the identity
criterion is numerical. The host checks structural binding, source custody,
transition consistency, normalizer identity and source-digest equality.

The deterministic result is:

| Layer | Result |
| --- | --- |
| Source manifest schema/provenance/custody/transition | valid |
| Structural target binding | admissible |
| Independent normalization | verified |
| Profile-relative result | `verified` |
| Historical PR #40 semantic identity | `not_evaluated` |

The JSON artifact is [pr45-source-backed-experiment.json](pr45-source-backed-experiment.json).

## Explicit non-claims

The public corpus slice does not contain the private historical Bonsai
successor contents. Therefore this experiment does not establish semantic
identity of the PR #40 output, does not create a PR #41
`SemanticAdjudicationReceipt`, and does not alter production admission. No
model-backed run is started.

The source manifest proves which host representation was inspected. It does
not prove that the representation is semantically correct. Likewise,
`verified` is relative to the named profile and normalizer contract; it is not
a universal Onto4 semantic verdict.

## Reproduction

From `apps/onto4-cli`:

```text
python research/pr45_source_backed_experiment.py \
  --output ../../docs/reports/pr45-source-backed-experiment.json
```

The regression tests execute `run_experiment()` without network access or
provider calls and verify digest reproducibility, the bounded case and all
non-claims above.
