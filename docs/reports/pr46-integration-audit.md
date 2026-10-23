# PR #46 — integration audit and one-turn interactive prototype

This research-only increment audits the path from the existing clarification
and assessment stack to the PR #40–#45 research contracts. It also runs one
bounded interactive turn against the local OpenAI-compatible endpoint. The
prototype records only redaction-safe lifecycle and semantic-status metadata.

## Integration map

The research stack has two parts:

- PRs #32–#37 establish the corpus, model-backed evaluation, context-aware
  interpretation, typed refinement, benchmark and bounded dialogue layers.
- PR #38 is merged into the research branch for bounded dialogue; it is not a
  merge into `main`.
- PR #39 is a sibling full-snapshot target experiment. PR #40–#46 form the
  research chain for explicit target binding, adjudication basis, independent
  normalization, source custody, source-backed normalization and integration
  smoke testing.

The live interactive path joins the first part at its host-controlled
orchestration boundary:

```text
provider JSON
  -> interpretation/schema checks
  -> host assessment and clarification question
  -> user answer
  -> host-bound successor/refinement
  -> reassessment
  -> deterministic landscape and Onto4 statuses
```

The provider supplies interpretation content only. The host owns snapshot
identity, pending-question identity, transition provenance and assessment. PR
#45's source-backed normalizer is not silently inserted into this production
interactive path; this prototype therefore does not create a source manifest,
semantic adjudication receipt or production admission.

## One-turn live run

The run used the public genome-identity question, the executable
`identity_and_genome` context and the frozen first-turn answer asserting
numerical identity. The public source is represented by its digest and length;
the answer is represented by a named frozen-fixture identifier. Arbitrary
answers passed to the runner do not receive a public fingerprint. Provider
payloads and credentials are not recorded.

The endpoint returned schema-valid responses for interpretation,
formalization, refinement and reassessment. The host issued one clarification,
accepted the successor transition as `structural_resolution`, and performed a
fresh assessment. With the bounded limit of one turn, the final state was:

| Field | Result |
| --- | --- |
| stop reason | `max_turns_reached` |
| disposition | `AskClarification` |
| landscape | `StableAcrossCandidates` |
| candidate assessments | two `Assessed` results |
| Onto4 verdicts | `U`, `U` |
| historical PR #40 identity | `not_evaluated` |

This is a successful integration smoke run, not a successful semantic
resolution. `U` here means that admitted formalizations did not establish a
`T`/`F` status; it is not a schema or transport failure. The host correctly
did not convert the model's refinement into a semantic receipt.

The redaction-safe artifact is
[pr46-interactive-prototype.json](pr46-interactive-prototype.json), and the
runner is
[pr46_interactive_prototype.py](/C:/_repoz/Onto4/apps/onto4-cli/research/pr46_interactive_prototype.py).

The artifact does not copy provider event details. Stage names, phases,
finish reasons, failure labels and elapsed time are normalized through closed
allowlists; unknown values become `unknown` or an empty detail. The endpoint
is reduced to scheme plus host and port. The frozen answer is represented by
its fixture ID; arbitrary answers receive no public fingerprint.

## Limits and next step

The one-turn result does not prove that a model can resolve the ambiguity. It
shows that the existing host loop preserves uncertainty when one turn is
insufficient. The PR #45 closed grammar remains a separate, frozen corpus
normalizer; it is not evidence about the live model's intended meaning.

PR #38 is merged into the research branch; PRs #32–#37 and #39–#46 remain
open Drafts. Before any sequential integration into `main`, the host should
verify the following dependency order and gates:

1. `main` → #32 → #33 → #34 → #35 → #36 → #37, with #38 already merged into
   the #37 research branch;
2. keep #39 as a sibling experiment rather than a prerequisite of #40;
3. integrate #40 → #41 → #42 → #43 → #44 → #45 → #46 only after exact-head
   CI, cumulative tests and a review that research modules remain outside
   production admission;
4. preserve the distinction between structural binding, profile-relative
   normalization, semantic adjudication receipt and production admission at
   each gate.

PR #46 itself does not merge the research modules into the production
pipeline. No new semantic-adjudication protocol or production-admission
change is justified by this smoke run.
