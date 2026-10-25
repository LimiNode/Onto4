# PR #59 — target-binding research synthesis

This synthesis is based only on the reviewed offline gate and the single
bounded live receipt in `pr58-binding-live-pilot.json`. It does not alter
production admission, clarification policy, or semantic adjudication.

The original PR #57 gate was permissive: it accepted broad status enumerations
and therefore was not sufficient evidence by itself. The corrected gate now
freezes the expected status tuple for every fixture and includes a negative
control that must fail when a valid outcome is tampered with. Historical gate
output is retained as evidence of the earlier protocol, not silently rewritten.

## Evidence boundary

The offline conformance gate established that binding validators distinguish
valid, stale, unknown, conflicting and unsupported claims. It did not evaluate
meaning. The live pilot used two frozen scenarios and three protocol conditions,
with exactly one call per cell. The model digest was unavailable and remains
`null`.

## Results

| axis | A — full snapshot | B — explicit binding | C — minimal envelope |
|---|---:|---:|---:|
| provider/schema-valid cells | 2/2 | 2/2 | 0/2 |
| catalog and lineage checks | 2/2 | 2/2 | not reached |
| literal target retained | 0/2 | 2/2 | unknown |
| independent semantic evidence | none | none | none |
| semantic correctness | not evaluated | not evaluated | not evaluated |

The bounded observation is therefore technical: in this run, the explicit
binding protocol retained the host target identifier in both schema-valid cells,
whereas the full snapshot did not. The minimal target-focused envelope was not
schema-valid in either cell. No cell supports a claim about whether the model
preserved the intended meaning.

## Interpretation and limits

Identifier retention is not semantic correctness. A catalog-valid identifier
can be attached to the wrong semantic object, and a missing identifier does not
prove that the clarification was misunderstood. Since there is no independent
semantic oracle here, the three conditions are not semantically comparable.

The C failures are a protocol/schema finding, not a semantic failure. C-v1 was
under-specified because its prompt omitted the source text and current
interpretation needed to construct a validated successor. This is a limitation
of that historical intervention, not evidence that Bonsai cannot support a
compact target-focused protocol. The run was not repeated to seek a more
favorable outcome. Historical receipts and the separate PR #39 line remain
unchanged.

## Decision

Do not promote any condition to production and do not create a semantic
adjudication receipt. The next architectural experiment should add a host-side,
independent semantic verification protocol (or a better-specified target-focused
envelope) while preserving host ownership of target identity. Until that oracle
exists, report technical binding conformance separately from semantic
interpretation and keep the evidence status `not_evaluated`.
