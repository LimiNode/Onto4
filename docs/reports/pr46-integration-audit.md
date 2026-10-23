# PR #46 — integration audit and one-turn interactive prototype

This research-only increment audits the path from the existing clarification
and assessment stack to the PR #40–#45 research contracts. It also runs one
bounded interactive turn against the local OpenAI-compatible endpoint. The
prototype records only redaction-safe lifecycle and semantic-status metadata.

## Integration map

The open Draft chain has two parts:

- PRs #32–#38 establish the corpus, model-backed evaluation, context-aware
  interpretation, typed refinement, benchmark and bounded dialogue layers.
- PR #39 is the sibling full-snapshot target experiment. PR #40–#45 form the
  research chain for explicit target binding, adjudication basis, independent
  normalization, source custody and source-backed normalization.

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
`identity_and_genome` context and one answer asserting numerical identity. The
source and answer are represented in the artifact only by SHA-256 digests and
lengths. Provider payloads and credentials are not recorded.

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

## Limits and next step

The one-turn result does not prove that a model can resolve the ambiguity. It
shows that the existing host loop preserves uncertainty when one turn is
insufficient. The PR #45 closed grammar remains a separate, frozen corpus
normalizer; it is not evidence about the live model's intended meaning.

All PRs #32–#45 remain Draft and unmerged. The next work item is an
integration review of this accumulated stack and a deliberately bounded
interactive scenario with an explicit policy for how many turns may be used.
No new semantic-adjudication protocol or production-admission change is
justified by this smoke run.
