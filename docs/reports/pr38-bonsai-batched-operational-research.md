# PR #38 — Bonsai batched operational research

## Scope and conclusion

This report covers the controlled Bonsai pilot and the corrective diagnostic
pass on the Stable Semantic Target Binding branch. It does not claim that the
model solved either philosophical case. The bounded corpus has no independent
final T/F/U/C oracle, and the pilot produced zero semantic-comparable
observations.

Baseline source: `e1057cca1c3e89809056c9082a2f8fd17ffe4732`  
Final source after the corrective pass: `3e64f5d3dd4bec59808aa53b3b812ed5cba532d5`  
Corpus: `bounded-dialogue-v1`, digest `ca77ec9fab468f267483918892c2a24799fab3242ceb0281857a917dbb826fb3`  
Target catalog: version `1`, digest `3fa40f87fcaa5766b1ee8ffad03f148892349cc5479dc08f77d46568223bc233`

The recommendation is **further research required**. PR #38 remains Draft and
must not be merged on the basis of this pilot.

## R0 — audited baseline

The original receipts were preserved unchanged. The 2×4 run used the fixed
condition order `A1, A2, B1, B2`, temperature `0`, thinking disabled and
`max_output_tokens=1024`. The backend was llama.cpp OpenAI-compatible `/v1`
with Bonsai 2 27B PQ2_0. No tariff was supplied, so every cost is `null` and
the report records `not_priced`.

| condition | execution | workflow | semantic | provider calls | known turns |
|---|---|---|---|---:|---:|
| A1 | 2 failed | 2 unverified | 2 not_comparable | 12 | 0 |
| A2 | 2 failed | 2 unverified | 2 not_comparable | 12 | 0 |
| B1 | 1 failed, 1 incomplete | 1 unverified, 1 incorrect | 2 not_comparable | 11 | 0 |
| B2 | 2 successful | 1 correct, 1 unverified | 2 not_comparable | 12 | 2 |

Across eight cells there were five operational failures, no semantic errors and
no semantic-comparable observations. The machine-readable stage matrix and
SHA-256 manifests are stored with the local artifacts:

- `artifacts/pr38-bonsai-20261019-10/stage-matrix.jsonl`;
- `artifacts/pr38-bonsai-20261019-10/artifact-digests.json`;
- `artifacts/pr38-bonsai-20261019-10/report.json`;
- `artifacts/pr38-bonsai-20261019-10/diagnostics.json`.

The preflight artifacts are under `artifacts/pr38-bonsai-20261019-09/`.

## R1 — output budget

The genome Full Snapshot preflight was run at 512 and 1024 output tokens, then
the two targeted cases were inspected at 1536 tokens.

| budget | interpretation | formalization | refinement | result |
|---:|---|---|---|---|
| 512 | schema-valid | schema-valid | `finish_reason=length`, schema failure | `schema_invalid` |
| 1024 | schema-valid | schema-valid | schema-valid | first refinement accepted, second target unverified |
| 1536 | schema-valid | schema-valid | schema-valid | same second-turn grounding failure |

The truncation occurred in `refinement`, not interpretation or formalization.
The larger budget removed the protocol failure but did not restore semantic
target provenance. Therefore 1024 is a minimum observed working budget for one
refinement, not a demonstrated robust dialogue budget. No validation was
weakened and no additional 2048 run was needed.

## R2 — second-turn target grounding

The redacted diagnostic trace shows the exact mechanism. The initial snapshots
contained host-issued target IDs. After the user's first answer, the model's
schema-valid Full Snapshot successors contained the same structural objects but
`target_id: null` for all ambiguities and ontology candidates. The host then
correctly refused to infer semantic family from positional IDs or wording, so
the next question became `family_unverified`.

This is a model grounding failure, not a missing host remapping. Automatically
copying the old target IDs would violate snapshot provenance and could bind a
new semantic object incorrectly. The redacted trace is
`artifacts/pr38-bonsai-20261019-11/full-snapshot-1536-redacted.json`.

## R3 — Typed Delta validation

The failing B1 genome proposal was captured with only its safe operation
structure:

```text
select_reading(
    target_id="ambiguity-0",
    resolved_ambiguity_ids=["ambiguity-0"]
)
```

The current refinement request allowed `reading-0` as a reading target and
`ambiguity-0` only as an ambiguity target. The host therefore rejected the
proposal with `RefinementValidationError`, classified as
`provenance_invalid`. This is the correct classification: it is neither an
unsupported Typed Delta capability nor a question-intent mismatch.

The deterministic regression is in `test_model_evaluation.py`, and the safe
diagnostic is `artifacts/pr38-bonsai-20261019-11/typed-delta-redacted.json`.

## R4 — script exhaustion

The B1 intrinsic-time trace shows two accepted transitions:

1. `select_reading(target_id="reading-0", resolved_ambiguity_ids=["ambiguity-0"])`;
2. `qualify_ontology_candidate(target_id="ontology-0", ...)`.

`qualify_ontology_candidate` changes the ontology description but is explicitly
recorded by the refinement layer as unresolved, not as an ontology selection
or final resolution. The host consequently presents the same ontology target
again on the successor snapshot. The frozen script has no third answer, so the
third selection is rejected as `script_exhausted`.

This is bounded operational incompleteness, not evidence of a broken progress
ledger and not grounds for silently adding a third scripted answer. The new
telemetry preserves the rejected question's safe ID, kind and target IDs.

## Corrective implementation

The only implementation change in this batch is diagnostic hardening in
`_ReplayPolicy.validate_issued()`: rejected selections, including exhausted
turns, now retain safe question identity in the workflow receipt. Two focused
regressions cover script-exhausted identity and the structural-ID/reading-ID
provenance violation. No oracle leakage, fallback remapping, new operation,
manager, registry, DTO or scorer framework was added.

Before the change, the baseline had 454 tests. After the change:

- Python 3.10/3.12 local suite: 456 passed;
- `compileall`: pass;
- `git diff --check`: pass.

The exact-head CI rerun for `3e64f5d3dd4bec59808aa53b3b812ed5cba532d5` is the
remaining publication gate.

## Interpretation and remaining blockers

The pilot establishes useful operational evidence:

- host-admitted first questions are possible;
- one Full Snapshot refinement can be accepted at 1024+ tokens;
- Typed Delta host validation rejects structural/semantic ID confusion;
- workflow completion can occur without semantic comparability.

It does not establish semantic accuracy. Remaining blockers are second-turn
model target grounding, Typed Delta model proposal reliability, and the need
for a versioned verdict-evaluation corpus if final T/F/U/C comparisons are
desired. The current bounded corpus intentionally leaves verdict comparability
at zero.

Latency is descriptive only: the 2×4 run used one fixed order and has no
permuted repeat. No architecture winner is declared. Model artifact digest and
prompt hash were unavailable from the endpoint/configuration and remain null;
the report records the exact model identifier, source SHA, catalog/context
digests, sampling settings, backend description, run ID and oracle version.

## Validation gate

The targeted Full Snapshot gate did not pass both scripted turns for either
case, so no additional 2×4 rerun was started after diagnosis. The existing
2×4 pilot remains a baseline, not a semantic benchmark. PR #38 stays Draft and
merge is intentionally not performed.
