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

```text
semantic_target_alignment: numerator 0 / denominator 0 / missing 12
status: not_evaluated
readiness: pending_independent_annotations
private_holdout_ready: false
verified_reviewer_count: 0
no_unresolved_disagreement: true
```

The runner accepts annotation records only when a host registry verifies the
reviewer identity, assignment, exact packet digest, rubric and evidence. A
reviewer may contribute at most one accepted submission per packet; duplicate
submissions are rejected. The trusted reviewer count is derived from distinct
stable identities represented by accepted attestations, not from registry
membership or caller-supplied aliases. The runner computes reviewer counts,
accepted/rejected attestations, disagreement and metric denominators from
those records rather than constants. This is a readiness result, not a
semantic score. The live-evaluation gate is false, no Bonsai calls were made,
and production authority is unchanged.
