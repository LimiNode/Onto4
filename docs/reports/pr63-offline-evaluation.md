# PR #63 — offline evaluation and calibration

PR #63 composes the frozen PR #61 corpus, PR #62 packet/annotation contract
and the existing PR #60 trusted-evidence verifier. It does not implement a
second semantic engine. The pipeline is:

```text
frozen inputs → blinded annotation contract → host evidence verification → research-only outcome
```

The deterministic negative controls cover exact trusted evidence, changed
snapshot reuse, omission mistaken for resolution, invalid verification mode,
provider-only evidence and the distinction between candidate annotations and
independent gold. Reviewer disagreement remains unresolved rather than being
converted into a majority truth.

The historical fixture corpus has 12 development cases and four disclosed
synthetic cases that were originally labelled holdout. Those four are not a
blind holdout. No private holdout or independent reviewer annotations are
present, so all semantic denominators are explicitly missing:

The development corpus is intentionally a disclosed, deterministic mechanics
fixture. Stable packet IDs and content digests bind annotations to content;
they do not provide secrecy or independent blind-holdout status.

```text
semantic_target_alignment: numerator 0 / denominator 0 / missing 12
status: not_evaluated
readiness: pending_independent_annotations
private_holdout_ready: false
verified_reviewer_count: 0
no_unresolved_disagreement: true
coverage: 0 / 12 consensus-supported cases
```

The runner accepts annotation records only when a host registry verifies the
reviewer identity, assignment, exact packet digest, rubric and evidence. A
reviewer may contribute at most one accepted submission per packet; duplicate
submissions are rejected. Abstentions are retained and counted, but only
completed non-abstaining judgments contribute semantic labels, reviewer
agreement or the minimum-two-reviewer coverage policy. The runner reports four
separate concepts: completed independent review, reviewer consensus, semantic
evidence sufficiency and authenticated live-evaluation readiness. Insufficient,
unavailable or contradictory evidence can therefore leave a covered case
indeterminate without turning it into a positive semantic result or a missing
review. The trusted reviewer count is derived from distinct stable identities
represented by accepted attestations, not from registry membership or
caller-supplied aliases. The live-evaluation gate is false, no Bonsai calls
were made, and production authority is unchanged.

Real readiness additionally requires a separately authenticated host registry
and private holdout, using the issuer-bound `HostTrustSource` capability.
`host_controlled=true`, a caller-created verifier object or a synthetic
mechanics pass is not sufficient evidence. The committed artifact has no
configured external trusted host source, so structurally valid caller metadata
cannot change the published false readiness result.

The optional synthetic gate mode exists only to exercise readiness mechanics;
its result is split into `synthetic_mechanics_passed` and
`synthetic_full_gate_passed`, and can never authorize live evaluation. Real
readiness requires a separately authenticated host-owned private holdout
manifest, two independent verified judgments for every development case and
no unresolved disagreement. Semantic evidence sufficiency remains an
independent reported dimension rather than an implicit coverage prerequisite.
