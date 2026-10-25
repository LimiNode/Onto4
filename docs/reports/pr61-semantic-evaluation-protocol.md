# PR #61 — Independent semantic evaluation protocol

This research protocol asks whether a clarification successor preserves the
meaning of the ambiguity that the host asked the model to resolve. It keeps
that question separate from literal target-ID retention and from structural
binding conformance. A successor may keep an identifier while changing the
meaning, or change an identifier while preserving the meaning.

The protocol is research-only. It creates no admission decision,
`SemanticAdjudicationReceipt` or production authority, and it makes no Bonsai
calls. The development corpus in
`apps/onto4-cli/research/pr61_semantic_evaluation_protocol.py` contains bounded
fixtures for testing the evaluator. Their expected labels are fixture
references, not independently established semantic gold.

## Frozen scope

The corpus has 16 cases from two families:

- seven genome-sharing / numerical-identity development cases;
- five intrinsic-present / observer-independent-time development cases;
- four holdout cases, two per family.

The required classes cover same and changed IDs, aligned and misaligned
successors, genuine resolution, mere omission, partial clarification,
unsupported ontological assertions, unrelated refinements, undecidable and
contradictory successors, and structurally changed but semantically equivalent
successors.

The holdout manifest publishes only aliases and integrity commitments. It does
not publish holdout text or expected labels. The holdout is frozen before any
later evaluator is adjusted against model output.

## Outcomes and abstention

Target alignment is one of `aligned`, `misaligned` or `indeterminate`.
Ambiguity resolution is one of `resolved`, `not_resolved`, `merely_omitted` or
`indeterminate`. Evidence is one of `sufficient`, `insufficient`,
`contradictory` or `not_available`.

An evaluator must abstain when the successor is ambiguous, evidence is missing
or contradictory, the case identity is stale, or the reviewer cannot identify
the intended target without importing an unstated ontology. Omission of an
ambiguous phrase is not resolution.

The primary outcome is semantic target alignment among independently reviewable
cases. Secondary outcomes are ambiguity resolution, literal ID retention,
structural binding conformance, unsupported-assertion rate and reviewer
agreement. Every aggregate must report its denominator and missing cases.

No claim of superiority is permitted from this small fixture corpus. A real
semantic result requires independently prepared annotations; otherwise the
status remains `pending_independent_annotations` or `not_evaluated`.

## Independence gate

The model/provider cannot assign its own gold label. An annotation prepared by
an agent or an LLM is `candidate_annotation`, never `independent_gold`.
Production-quality semantic evaluation requires at least two independent
reviewers, blinded to condition, model identity, target-ID equality and binding
verdict. Until that gate is met, later offline controls may run, but no live
Bonsai result may be called independently semantically correct.

The next stacked protocol may consume this schema, but it must not modify the
frozen corpus or holdout after inspecting model output.
