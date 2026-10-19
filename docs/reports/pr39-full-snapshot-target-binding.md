# PR #39 — Full Snapshot semantic target binding experiment

## Scope

This report records a bounded experiment after PR #38. It asks one narrow
question: when a Full Snapshot refinement starts from an immutable snapshot
whose semantic targets are already host-bound, does the model preserve those
public `target_id` values across successive refinements?

This is an isolated provider experiment, not a change to Onto4 admission
rules. It does not inherit an ID that the model omitted, infer an ID from a
structural position, or expose an evaluation oracle to the model.

Source after PR #38 merge: `d969338ee040e304e4dc1afb0f3aa1a373604967`  \
Model: Bonsai 2 27B PQ2_0 through the local llama.cpp OpenAI-compatible
`/v1` endpoint  \
Model artifact digest: unavailable from endpoint  \
Prompt version: `pr39-target-binding-v1`  \
Sampling: temperature `0`, thinking disabled, maximum output `4096` tokens  \
Context digests: not applicable to the host-bound fixture protocol  \
Semantic oracle: none; target preservation only  \
Historical run identifier: `pr39-bonsai-20261019-target-binding-full-snapshot-1536`  \
Matched run identifiers: `pr39-bonsai-20261019-target-binding-e2e-4096-corrected`,
`pr39-bonsai-20261019-target-binding-two-turn-4096-corrected-v2`

## Protocol

The controlled initial `InterpretationSpace` contained one ambiguity, one
ontology candidate and one reading. The host-bound public catalog and the
two questions matched the frozen corpus exactly:

| case | turn 1 | turn 2 |
| --- | --- | --- |
| genome identity | Meaning → `ambiguity-genome` | Meaning → `ambiguity-criterion` |
| intrinsic time | Meaning → `ambiguity-present` | Ontology → `ambiguity-observer` |

The host issued the first question, accepted the successor snapshot, then
issued the second question against that successor. Full Snapshot was called
independently for each transition. The host retained the existing strict
provenance checks; the experiment only observed the returned target IDs.

## Results

### Historical 1536-token baseline

The ordinary bounded-dialogue run used the public corpus and target catalog at
1536 output tokens. Both cases produced schema-valid refinements, but both
ended as `question_intent_unverified` with `family_unverified`. The selected
questions carried structural IDs such as `ambiguity-0`, while the successor
snapshots did not provide the corresponding public semantic target binding.
No case reached reassessment and no semantic-comparable observation was
created. This run is retained as a historical baseline only.

### Matched 4096-token E2E run

The ordinary bounded-dialogue runner was then executed at the same 4096-token
budget as the isolated protocol. Both cases again ended as
`question_intent_unverified` with `family_unverified`; no case reached
reassessment and no semantic-comparable observation was created. This is the
budget-matched E2E comparison used below.

### Host-bound isolated two-turn run

| case | transitions | provider-valid | target preserved after turn 1 | target preserved after turn 2 | host workflow admission |
| --- | ---: | ---: | --- | --- | --- |
| genome identity | 2 | 1 | no (retargeted) | not reached | not evaluated |
| intrinsic time | 2 | 2 | yes | yes | not evaluated |

The intrinsic-time case had two schema-valid provider successors with valid
transition provenance and preserved both public IDs. In the genome case, the
first provider successor parsed and passed transition provenance but changed
the ambiguity binding from
`ambiguity-genome` to `ambiguity-criterion`; the second transition then failed
schema validation. The questions were synthetic fixtures, not selections made
by a live `FixtureClarificationPolicy`, `_ReplayPolicy`, progress-aware policy
or reassessment loop. Consequently `host_workflow_admission` is explicitly
`not_evaluated` for every isolated turn. These are synthetic preservation
observations because the initial snapshots were host-bound; they are not
evidence that the frozen corpus produced those bindings.

This result is conditional: the model was given a host-bound initial snapshot,
the public catalog was present in the refinement prompt, and the run did not
evaluate a final T/F/U/C verdict. It demonstrates preservation capability, not
end-to-end grounding or semantic correctness.

### Budget sensitivity

An exploratory isolated call at 1536 tokens terminated with
`finish_reason=length` before a successor JSON object was available. It is
classified as execution/schema failure, not as semantic target loss. The
matched comparison uses 4096 tokens for both ordinary E2E and isolated
protocol. The 1536 E2E result remains a historical baseline and is not mixed
into the matched metrics. No latency or quality winner is claimed.

The published JSON is a curated redacted summary. Its `source_receipts` section
records SHA-256 digests for the local E2E report, E2E receipts and isolated
runner output. Prompts, raw model payloads, credentials and local filesystem
paths were removed; the summary retains only safe stage outcomes, target IDs
and provenance flags.

## Conclusion

The matched experiment separates three failure modes that were conflated in the
Bonsai pilot:

1. In the ordinary E2E path, the model may produce a structurally valid
   successor without a public semantic binding; the host correctly refuses to
   call that a verified target-family match.
2. Given a host-bound initial snapshot and sufficient output budget, Bonsai can
   preserve the supplied semantic IDs across two Full Snapshot transitions for
   the intrinsic-time fixture. This is provider-level evidence only; host
   workflow admission was not evaluated.
3. The same protocol can pass parsing and transition provenance while changing a
   valid target to the wrong valid target, as in genome turn 1. A valid public
   ID is therefore not by itself evidence of correct target provenance.

No production behavior is changed by this report. In particular, Onto4 must
not automatically copy a missing successor `target_id` from a prior snapshot.
The next experiment should test whether an explicit host-issued target-binding
operation can be admitted without turning structural position into semantic
identity. Until that protocol is specified and independently evaluated, the
E2E target-binding failure remains unresolved. The redacted machine-readable
evidence is in
`docs/reports/pr39-full-snapshot-target-binding-evidence.json`; the executable
fixture runner is
`apps/onto4-cli/research/pr39_target_binding_runner.py`.
