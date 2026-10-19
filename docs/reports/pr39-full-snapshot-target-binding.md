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
Run identifiers: `pr39-bonsai-20261019-target-binding-full-snapshot-1536`,
`pr39-bonsai-20261019-target-binding-isolated-4096`,
`pr39-bonsai-20261019-target-binding-two-turn-4096`

## Protocol

The controlled initial `InterpretationSpace` contained one ambiguity, one
ontology candidate and one reading. The ambiguity and ontology candidate were
bound to public catalog entries before the provider call:

- genome case: `ambiguity-genome` and `ambiguity-observer`;
- intrinsic-time case: `ambiguity-present` and `ambiguity-observer`.

The host issued one Meaning question, accepted the successor snapshot, then
issued one Ontology question against that successor. Full Snapshot was called
independently for each transition. The host retained the existing strict
provenance checks; the experiment only observed the returned target IDs.

## Results

### E2E baseline

The ordinary bounded-dialogue run used the public corpus and target catalog at
1536 output tokens. Both cases produced schema-valid refinements, but both
ended as `question_intent_unverified` with `family_unverified`. The selected
questions carried structural IDs such as `ambiguity-0`, while the successor
snapshots did not provide the corresponding public semantic target binding.
No case reached reassessment and no semantic-comparable observation was
created.

### Host-bound isolated two-turn run

| case | transitions | accepted | Meaning ID preserved after turn 1 | preserved after turn 2 | Ontology ID preserved after turn 1 | preserved after turn 2 |
| --- | ---: | ---: | --- | --- | --- | --- |
| genome identity | 2 | 2 | yes | yes | yes | yes |
| intrinsic time | 2 | 2 | yes | yes | yes | yes |

All four Full Snapshot transitions were schema-valid and accepted. Structural
IDs remained stable in this fixture, and the public semantic IDs were retained
in every successor returned by the model.

This result is conditional: the model was given a host-bound initial snapshot,
the public catalog was present in the refinement prompt, and the run did not
evaluate a final T/F/U/C verdict. It demonstrates preservation capability, not
end-to-end grounding or semantic correctness.

### Budget sensitivity

An exploratory isolated call at 1536 tokens terminated with
`finish_reason=length` before a successor JSON object was available. It is
classified as execution/schema failure, not as semantic target loss. The
successful two-turn result therefore uses 4096 tokens and must not be compared
as a latency or quality win against the 1536 E2E baseline.

## Conclusion

The experiment separates two failure modes that were conflated in the Bonsai
pilot:

1. In the ordinary E2E path, the model may produce a structurally valid
   successor without a public semantic binding; the host correctly refuses to
   call that a verified target-family match.
2. Given a host-bound initial snapshot and sufficient output budget, Bonsai can
   preserve the supplied semantic IDs across two Full Snapshot transitions.

No production behavior is changed by this report. In particular, Onto4 must
not automatically copy a missing successor `target_id` from a prior snapshot.
The next experiment should test whether an explicit host-issued target-binding
operation can be admitted without turning structural position into semantic
identity. Until that protocol is specified and independently evaluated, the
E2E target-binding failure remains unresolved.
