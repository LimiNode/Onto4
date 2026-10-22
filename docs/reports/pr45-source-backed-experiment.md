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

The separately implemented `pr45_independent_corpus_normalizer` reads the
answer text and derives the one profile-relevant commitment. Its frozen rubric
recognizes explicit assertions of numerical identity as `affirmed`, explicit
assertions of genetic similarity or a rejection of numerical identity as
`denied`, and leaves other wording `unspecified`. The host then checks
structural binding, source custody, transition consistency, normalizer
identity and source-digest equality.

This is a content-sensitive normalization procedure, rather than a commitment
written by the experiment runner. It is deliberately narrow: it establishes
the behavior of this documented rubric for this frozen case, not general
natural-language semantic adjudication.

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

## Negative control

The regression suite replaces the answer with “I mean genetic similarity, not
numerical identity.” The normalizer derives `denied` from that changed source,
and the profile result becomes `contradicted`, never `verified`. The suite
also checks that the published JSON artifact exactly equals a fresh
`run_experiment()` result.

## Reproduction

From `apps/onto4-cli`:

```text
python research/pr45_source_backed_experiment.py --output ../../docs/reports/pr45-source-backed-experiment.json
```

The regression tests execute `run_experiment()` without network access or
provider calls and verify digest reproducibility, content-sensitive negative
control, artifact reproducibility, the bounded case and all non-claims above.
