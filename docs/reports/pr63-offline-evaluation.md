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

The development corpus has 12 cases and the frozen holdout has four. Since no
independent reviewer annotations or independently established gold reference
are present, all semantic denominators are explicitly missing:

```text
semantic_target_alignment: numerator 0 / denominator 0 / missing 12
status: not_evaluated
readiness: pending_independent_annotations
```

This is a readiness result, not a semantic score. The live-evaluation gate is
false, no Bonsai calls were made, and production authority is unchanged.
