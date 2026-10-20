# PR #40 — Semantic Target Binding Protocol

This is a research-only protocol built on the merged PR #38 baseline. It
tests whether a provider can make a bounded claim about the relation between
two immutable `InterpretationSpace` snapshots without making that claim a
semantic oracle.

## Why an ID is not enough

An identifier can be valid in the host catalog while pointing at the wrong
semantic object. Conversely, a new description can preserve an intended object
without providing enough evidence for the host to declare semantic identity.
The protocol therefore reports structural evidence separately:

1. the provider response has the expected schema;
2. the target exists in the public host catalog and has the expected kind;
3. both snapshot references belong to the issued transition;
4. the claimed relation is admissible for the host-issued question and the two
   snapshots;
5. semantic identity is `unverified` unless an independent adjudicator exists.

The host never inherits an omitted ID, remaps a positional ID, or treats a
provider assertion as proof of meaning. `no_binding` is an explicit,
non-comparable outcome.

## Protocol surface

`onto4.pipeline.semantic_binding` defines a small immutable protocol:

- `SemanticTargetCatalog` contains host-owned public IDs and their `Meaning` or
  `Ontology` kind;
- `BindingTransition` contains the previous snapshot, current snapshot and
  the exact host-issued question;
- `BindingClaim` is parsed from provider JSON and supports `preserve`,
  `anchored_update`, `create` and `no_binding`;
- `BindingEvaluation` records independent `schema`, `catalog`, `lineage`,
  `transition` and `semantic_identity` results.

`anchored_update` requires the same source and destination target ID and the
target to exist in both snapshots. `create` requires the target to be new in
the current snapshot and does not carry a source target ID. A `preserve` claim
also names the same source target as its destination, so a claim that points
at another valid ID is rejected. Snapshot target IDs are checked before these
relations are evaluated: duplicates and conflicting `Meaning`/`Ontology`
kinds are invalid rather than silently normalized by a dictionary.

The explicit-binding runner accepts exactly the outer keys `successor` and
`binding_claim`; private oracle fields and arbitrary additions fail closed. Its
`prompt_template_digest` is the SHA-256 digest of the canonical prompt
template used by the runner. It is not a hash of the human-readable version
label and is not a hash of a provider response.

## Deterministic validation matrix

The regression suite covers:

- missing IDs and unknown IDs;
- a wrong but catalog-valid target of the same kind;
- permutation of two valid `Meaning` targets;
- cross-kind binding;
- duplicate/conflicting claims;
- `preserve` pointing at a different source target;
- duplicate snapshot IDs and conflicting snapshot kinds;
- stale snapshot lineage;
- changed semantic text with structural success still marked
  `semantic_identity=unverified`;
- attempted inheritance of an existing ID through `create`;
- non-empty `source_target_id` on `create` at the schema boundary;
- explicit `no_binding`;
- rejection of private oracle fields in model-facing claims;
- valid `Ontology` binding.

The deterministic suite now contains 19 checks: 5 acceptance/metadata checks
and 14 negative regressions. These tests validate the protocol boundary, not
final T/F/U/C correctness.
The bounded pilot used the same two frozen cases and `4096` output-token
budget for one Full Snapshot and one explicit-binding call per case.

The first explicit-binding prompt produced a schema failure in both cases:
the model added `target_id`/`term` fields to presuppositions. That run is kept
as a protocol-discipline baseline and was not counted as a semantic failure.
After the prompt was made exact about every nested JSON shape, the repeat run
produced:

| case | Full Snapshot | explicit binding |
| --- | --- | --- |
| genome identity | provider-valid, target absent | provider-valid, structural checks valid, semantic identity unverified |
| intrinsic time | provider-valid, target absent | provider-valid, structural checks valid, semantic identity unverified |

Host workflow admission was not evaluated and no semantic oracle was supplied.
The explicit-binding result therefore demonstrates a structurally admissible
claim, not semantic equivalence of the returned text. The published pilot
receipts remain historical artifacts; the corrective pass does not rewrite
their model outputs or provenance fields.

## Current status

- Baseline: `d969338ee040e304e4dc1afb0f3aa1a373604967` (merged PR #38).
- Structural corrective pass implementation: `2ea587a324a8987adea49d1510e62c6cd3dfbc9f`.
- Exact-head CI for that implementation: `39443827968` (Python 3.10/3.12) — success.
- Production admission: unchanged.
- Automatic target-ID inheritance: prohibited.
- Model-backed pilot: bounded paired run completed; no final T/F/U/C oracle.
- Pilot run IDs: `pr40-bonsai-20261020-semantic-binding-paired-4096` and
  `pr40-bonsai-20261020-semantic-binding-paired-4096-v2`.
- Redacted machine-readable outputs: `pr40-semantic-target-binding-pilot.json`
  and `pr40-semantic-target-binding-pilot-v2.json`.
- The corrective pass adds no new model run and leaves both receipts intact;
  future runner output records `prompt_template_digest` instead of the former
  version-label `prompt_hash`.
