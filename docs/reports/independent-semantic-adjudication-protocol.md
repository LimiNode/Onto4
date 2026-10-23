# Independent Semantic Adjudication Protocol

This is a research-only companion to PR #40. It answers a narrower question
than structural binding:

> When a provider claims that a target survived a transition, what evidence
> would allow a host to record semantic identity as verified?

The answer cannot be obtained from the provider's binding claim alone. A valid
ID, target kind, lineage and transition relation show that the provider named
the intended host object. They do not show that the returned interpretation
still carries the intended meaning.

## The distinction that must remain visible

Consider the target `ambiguity-genome`. The host question asks whether two
people who share a genome are one person in the numerical-identity sense. A
provider can return a structurally valid `anchored_update` for that target and
then explain genetic similarity instead of numerical identity. The target ID
survived, but the semantic content may not have.

PR #40 records that gap as `semantic_identity=unverified`. This protocol adds
an independent adjudication receipt; it does not infer identity from text
similarity, target descriptions or provider confidence.

## Receipt contract

The host keeps the adjudication basis outside provider-facing input. The basis
may be a versioned rubric, a human panel record or another explicitly named
profile-specific procedure. The host publishes only its SHA-256
`basis_digest` when recording the receipt.

`onto4.pipeline.semantic_adjudication` accepts a receipt with exactly these
fields:

- the previous and current snapshot IDs;
- the target ID and binding relation being assessed;
- an adjudication decision: `verified`, `contradicted`, `unverified` or
  `not_comparable`;
- an `adjudicator_id` and `adjudicator_version`;
- the host-owned `basis_digest`.

The evaluator checks four separate conditions:

1. the receipt has the exact schema;
2. its snapshots, target and relation match the structurally admissible
   binding claim and issued transition. The binding evaluation itself must
   carry the same snapshot IDs and host question identity;
3. its basis digest matches the host-owned basis for this run;
4. the adjudicator identity differs from the provider identity and matches a
   host-owned trusted registry with the recorded `adjudicator_version`, and the
   host separately attests that the receipt arrived through that trusted
   channel. The receipt cannot self-assert this authority.

Only a receipt that passes all four checks can produce `verified` or
`contradicted`. A missing receipt, a structurally invalid binding or a failed
provenance/independence check is `not_comparable`; it cannot upgrade a claim.

## What this protocol does not establish

The module validates a receipt and its provenance. It does not decide whether
the adjudicator's rubric is philosophically correct, whether a private panel
is competent, or whether one profile is the universal Onto4 semantics. Those
are separate research questions.

The decision values are adjudication evidence, not Onto4 `T`, `F`, `U` or `C`
verdicts. In particular, `unverified` means that this receipt does not settle
semantic identity; it does not mean that the provider's text is false.

The receipt is host-side evidence. It must not be added to the provider's
binding envelope, and the evaluator does not rewrite the provider claim or
admit a successor snapshot.

## Deterministic boundary tests

The first bounded implementation has sixteen tests covering:

- a valid independent receipt;
- an explicitly contradicted receipt;
- same-actor provider/adjudicator rejection;
- untrusted adjudicator identities and versions;
- an unattested receipt origin;
- reuse of a binding evaluation for another transition or question;
- stale snapshot lineage;
- target/relation mismatch;
- basis-digest mismatch;
- structural binding failure that cannot be upgraded;
- missing receipt;
- private receipt fields;
- malformed basis digests.

These tests establish the provenance boundary. They do not claim that an
adjudicator has already verified the two Bonsai cases from PR #40, and they do
not add a model-backed run or production admission.

## Current scope

The implementation is isolated from PR #40's production path. The next step is
to define and independently review one concrete, profile-relative adjudication
basis, then run a bounded experiment whose receipt and basis provenance can be
published without exposing private oracle content. Until that exists, PR #40's
`semantic_identity=unverified` result remains unchanged.
