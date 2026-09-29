# Onto4 operator tables (canonical strict profile)

This document is the executable-style specification of the canonical strict
operator profile. Onto4 first checks whether a proposition is well formed in a
pinned semantic context, then evaluates its truth status. `C` is the result of
semantic admissibility failing; it is not missing evidence and it is not a
synonym for an absent object.

The four verdicts are:

| Symbol | Meaning |
| --- | --- |
| `T` | well formed and true under the selected context |
| `F` | well formed and false under the selected context |
| `U` | well formed, but `T`/`F` is not established in this context |
| `C` | not well formed under the selected ontology/semantic profile |

## Semantic checking and evaluation

The semantic checker covers the whole AST before the canonical operator table
is applied. Therefore a category error in any required sub-expression remains
visible in the strict result.

The canonical profile is **strict**. It is defined by the complete tables below,
including every combination with `C`. This makes the tables suitable as a
reference for implementations, fixtures and audit/replay checks.

An evaluator may additionally expose an operational **determining/short-circuit
projection**. For example, `T ∨ X` can determine a query answer without
evaluating `X`, and `F ∧ X` can do the same. That projection is an
optimization at the query/evaluation layer, not a replacement for the strict
assessment. The skipped branch, context and either its diagnostics or an
explicit `semantic_check_deferred` marker must be retained.

Strict assessment answers: *is this complete formal proposition admissible, and
what verdict follows from it?* Determining projection answers a narrower
operational question: *what result is already determined by the part evaluated
so far?*

## Negation

| `A` | `¬A` |
| --- | --- |
| `T` | `F` |
| `F` | `T` |
| `U` | `U` |
| `C` | `C` |

Negation does not turn a category error into a meaningful proposition.

## Conjunction

| `A ∧ B` | `T` | `F` | `U` | `C` |
| --- | --- | --- | --- | --- |
| **`T`** | `T` | `F` | `U` | `C` |
| **`F`** | `F` | `F` | `F` | `C` |
| **`U`** | `U` | `F` | `U` | `C` |
| **`C`** | `C` | `C` | `C` | `C` |

## Disjunction

| `A ∨ B` | `T` | `F` | `U` | `C` |
| --- | --- | --- | --- | --- |
| **`T`** | `T` | `T` | `T` | `C` |
| **`F`** | `T` | `F` | `U` | `C` |
| **`U`** | `T` | `U` | `U` | `C` |
| **`C`** | `C` | `C` | `C` | `C` |

The strict result is `C` whenever either operand is `C`, even when an
operational evaluator could determine a `T` or `F` branch without evaluating the
other operand.

## Implication

The canonical definition is:

```text
A → B = ¬A ∨ B
```

with strict `C` propagation. Its complete table is:

| `A → B` | `T` | `F` | `U` | `C` |
| --- | --- | --- | --- | --- |
| **`T`** | `T` | `F` | `U` | `C` |
| **`F`** | `T` | `T` | `T` | `C` |
| **`U`** | `T` | `U` | `U` | `C` |
| **`C`** | `C` | `C` | `C` | `C` |

A profile that wants a different treatment of `C` must declare implication as a
separate primitive connective and publish a different full table; it must not
claim the definition above while using incompatible entries.

## Equivalence

The default equivalence is derived, not an independent primitive:

```text
A ↔ B = (A → B) ∧ (B → A)
```

The resulting complete table is:

| `A ↔ B` | `T` | `F` | `U` | `C` |
| --- | --- | --- | --- | --- |
| **`T`** | `T` | `F` | `U` | `C` |
| **`F`** | `F` | `T` | `U` | `C` |
| **`U`** | `U` | `U` | `U` | `C` |
| **`C`** | `C` | `C` | `C` | `C` |

Any profile that chooses a primitive equivalence must document where it differs
from this derived form and test the difference.

## Determining projection (operational note)

The following is not a second truth table. It records useful operational
projections while the canonical strict result remains unchanged:

| Expression at short-circuit time | Operational projection | After complete semantic check |
| --- | --- | --- |
| `T ∨ X` | `T` before `X` is evaluated | `C` if `X` checks as `C`; otherwise the ordinary strict result |
| `F ∧ X` | `F` before `X` is evaluated | `C` if `X` checks as `C`; otherwise the ordinary strict result |
| `T ∨ U` | `T` | `T` |
| `F ∧ U` | `F` | `F` |

The first two rows describe an as-yet unchecked branch, not a branch already
known to be `C`. If the later semantic check returns `C`, the canonical result
is `C`; if it returns a meaningful verdict, the corresponding strict table
applies. The operational result must carry the skipped branch and its deferred
or completed semantic diagnostic.

## Open algebraic obligations

For the canonical strict profile, `∧` and `∨` remain commutative and associative
over all four values; both De Morgan laws and both distributive laws hold.
Once `C` is included as a propagated semantic failure, absorption is not a law
of the whole four-valued profile; for example:

```text
A ∧ (A ∨ C) = C, not A
```

This is an explicit limitation of semantic-error lifting, not a reason to
silently place `C` into the truth or information lattice. Evidence conflict
belongs to a separate `Evidence4` axis (`Neither`, `TrueOnly`, `FalseOnly`,
`Both`) and must not be encoded by changing `U` into `C`.
