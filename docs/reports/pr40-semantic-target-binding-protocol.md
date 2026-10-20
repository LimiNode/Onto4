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
the current snapshot. A `preserve` claim also names its source target so a
permutation of two valid IDs is rejected.

## Deterministic validation matrix

The regression suite covers:

- missing IDs and unknown IDs;
- a wrong but catalog-valid target of the same kind;
- permutation of two valid `Meaning` targets;
- cross-kind binding;
- duplicate/conflicting claims;
- stale snapshot lineage;
- changed semantic text with structural success still marked
  `semantic_identity=unverified`;
- attempted inheritance of an existing ID through `create`;
- explicit `no_binding`;
- rejection of private oracle fields in model-facing claims;
- valid `Ontology` binding.

These tests are deliberately offline. They validate the boundary, not a model
and not final T/F/U/C correctness. A future bounded model pilot must report
provider schema success, catalog/kind validity, lineage, transition admission,
binding conflicts and semantic identity independently, and must preserve
`unverified` when no independent semantic adjudication is available.

## Current status

- Baseline: `d969338ee040e304e4dc1afb0f3aa1a373604967` (merged PR #38).
- Production admission: unchanged.
- Automatic target-ID inheritance: prohibited.
- Model-backed pilot: not run in this initial protocol commit.
