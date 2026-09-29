# Onto4 operator tables (draft profile)

This document records a **draft operator profile**, not a settled algebra.
Onto4 first checks whether a proposition is well formed in a pinned semantic
context. `C` is the result of that check failing (a category error); it is not
missing evidence and it is not a synonym for an absent object. A proposition
about an object that is simply false is `F` when the object and predicate are
well typed.

The four verdicts are:

| Symbol | Meaning |
| --- | --- |
| `T` | well formed and true under the selected context |
| `F` | well formed and false under the selected context |
| `U` | well formed, but `T`/`F` is not established in this context |
| `C` | not well formed under the selected ontology/semantic profile |

## Semantic checking and evaluation

`C` is produced by a typed semantic checker before logical evaluation. A
compound expression therefore has two possible implementation profiles:

1. **Strict assessment (recommended for proofs and audit):** report `C` with
   diagnostics whenever an operand or required sub-expression is a category
   error; do not allow a convenient `T` or `F` branch to hide it.
2. **Operational short-circuit:** an evaluator may return `T` for `T ∨ X` or
   `F` for `F ∧ X`, but it must retain the skipped branch and its diagnostic.

The second profile is an evaluation optimisation, not a replacement for the
strict assessment. The profile, diagnostics and skipped branches must be
recorded in a replayable result.

### Why strict is canonical

Strict semantics is the canonical object-level profile because it prevents a
determining branch from laundering an invalid category. It preserves
compositionality, diagnostics and replay: the result describes the whole AST,
not only the part that happened to determine a Boolean answer.

Example:

```text
A = Existed(grandfather, reconstructed_past)       -> T
B = WasAbsolutely(grandfather)                     -> C
A ∨ B                                               -> C   (strict)
```

The `T` branch does not make the malformed `B` disappear. A determining
evaluator may use `T ∨ X = T` to answer a bounded query without evaluating `X`,
but it must return an operational projection carrying the skipped branch and
the strict diagnostic. This is useful for query resolution, search, and
candidate selection; it is not a replacement for the canonical assessment.

Candidate selection is a meta-level operation. Given `F1 -> T` and `F2 -> C`,
the statement “at least one admissible formalization exists” may select `F1`;
it must not be represented as the object-level formula `F1 ∨ F2`.

## Negation

```text
¬T = F    ¬F = T    ¬U = U    ¬C = C
```

Negation does not turn a category error into a meaningful proposition.

## Conjunction and disjunction

For the strict assessment profile, `C` is propagated before the ordinary
three-way evaluation:

```text
A ∧ B = C  if A = C or B = C
A ∨ B = C  if A = C or B = C
```

Otherwise use the following `T/F/U` tables:

| A | B | `A ∧ B` | `A ∨ B` |
|---|---|---|---|
| T | T | T | T |
| T | F | F | T |
| F | F | F | F |
| T | U | U | T |
| F | U | F | U |
| U | U | U | U |

An implementation may expose short-circuit identities such as `F ∧ X = F`
and `T ∨ X = T`, but strict assessment still evaluates or records the other
branch for category diagnostics.

## Implication

The strict profile defines implication only after the category check:

```text
A → B = ¬A ∨ B       when A and B are not C
A → B = C            when A = C or B = C
```

For non-`C` operands:

| A | B | `A → B` |
|---|---|---|
| T | T | T |
| T | F | F |
| F | T | T |
| F | F | T |
| T | U | U |
| U | T | T |
| U | U | U |

If a different profile wants `F → C = T` or another treatment of `C`, it must
declare implication as a separate primitive connective and publish its full
truth table; it must not claim the definition above while using an
incompatible table.

## Equivalence

The default definition is derived, not an independent primitive:

```text
A ↔ B = (A → B) ∧ (B → A)
```

Any profile that chooses a primitive equivalence must document where it differs
from this derived form and test the difference.

## Open algebraic obligations

Before these operators are used as a theorem system, the project must choose a
named profile and test the properties it claims: associativity,
commutativity, De Morgan laws, distributivity, implication laws and the
relationship to any information ordering. Evidence conflict belongs to a
separate `Evidence4` axis (`Neither`, `TrueOnly`, `FalseOnly`, `Both`); it must
not be encoded by silently changing `U` into `C`.
