# Onto4

**Onto4** is a context-bound four-valued logic. It distinguishes not only
true, false and unresolved propositions, but also the case where the checked
formulation has no admissible meaning in the selected ontology or semantic
profile.

In ordinary reasoning we ask:

- Is this true?
- Is this false?
- Or do we not know yet?

There is a prior question that is easy to miss: **can this proposition be
meaningfully formulated in the adopted system of concepts?** Sometimes the
problem is not a wrong answer but the conceptual space in which the question
was posed.

> Not every assertion has meaning in every context. Before asking whether it is
> true or false, ask whether it is admissible as a proposition at all.

## Four verdicts

| Verdict | Meaning |
| --- | --- |
| `T` | the formulation is well formed and true in the selected context |
| `F` | the formulation is well formed and false in the selected context |
| `U` | the formulation is meaningful, but `T`/`F` is not established here |
| `C` | the checked formulation is not semantically admissible here (category error) |

The central distinction is:

```text
U: the question has meaning, but its answer is not established.
C: the adopted ontology or semantic profile does not admit this formulation.
```

`C` is not a synonym for missing data, an absent object or an ordinary false
claim. A proposition about a non-existent object can still be `F` when its term,
predicate and domain are well typed. `C` records a failure of semantic
admissibility: undefined references, incompatible sorts, missing categories,
unsupported presuppositions or an inapplicable predicate.

## Why the fourth verdict matters

Consider two ways to talk about a grandfather in a reconstructed past:

```text
ExistsAt(grandfather, t)                 -> T, F or U
WasAbsolutely(grandfather)               -> C
```

The first relation can be interpreted over a time model and assessed with
available evidence. The second asks for an absolute, model-independent
property that the selected ontology may not define. Its problem is not that the
grandfather did not exist; the problem is that this way of posing the question
has no admissible interpretation in the chosen ontology.

The same distinction appears in identity across time:

```text
Continuity(me_child, me_now)             -> T, F or U
SamePersistentSubstance(me_child, me_now)-> C  (if that category is absent)
```

Onto4 can therefore put the category used to formulate a question under review,
not only the answer obtained from it.

## Context-bound meaning

The same text can receive different verdicts under different contexts. A
context fixes an ontology, language, semantic conventions, evidence policy and
perspective:

```text
meaning : Statement × Context -> Onto4Verdict
```

A conceptual representation may look like:

```cpp
struct ContextFrame {
    OntologyProfile ontology;
    SemanticProfile semantics;
    EpistemicProfile epistemics;
    InferenceProfile inference;
    Perspective perspective;
};
```

For example, `InternetExists` can be `C` in a profile where the term is
undefined, while a profile that explicitly interprets the term retrospectively
may yield `F` or `U`. The difference is semantic definition, not merely lack of
evidence.

## Onto4 and Evidence4

Onto4 describes semantic status. Evidence is tracked on a separate
Belnap–Dunn-like axis:

```text
Neither | TrueOnly | FalseOnly | Both
```

Thus `Onto4 = U` with `Evidence4 = Neither` and `Onto4 = U` with
`Evidence4 = Both` are different evidence situations, but both propositions can
remain meaningful. `Both` is not `C`, and evidence conflict must not be encoded
by silently changing `U` into `C`.

## Canonical strict semantics

The canonical Onto4 profile is **strict**. Semantic checking covers the whole
AST before truth evaluation, so a category error in any required operand remains
visible:

```text
¬C = C
C ∧ X = C
C ∨ X = C
C → X = C
X → C = C
```

This prevents a determining branch from hiding an invalid ontology or a hidden
presupposition. Strict semantics answers: *is this complete formal proposition
admissible, and what verdict follows from it?*

An operational **determining/short-circuit projection** is still useful. For
example, `T ∨ X` or `F ∧ X` may determine a query result before the other branch
is evaluated. That is an evaluation optimisation, not a replacement for the
strict verdict. The skipped branch, its context and its semantic diagnostic (or
an explicit `semantic_check_deferred` marker) must be retained.

## Operator tables

The complete strict tables for negation, conjunction, disjunction, implication
and derived equivalence are maintained as an executable-style specification:

- [English operator tables](docs/truth-tables.md)
- [Russian operator tables](docs/truth-tables-ru.md)

The tables include every combination with `C`. The determining projection is
documented separately beside them; it never changes the canonical strict
result.

## Relation to other logics

| Logic | Values | Semantic inadmissibility | Indeterminacy | Self-reference |
| --- | --- | --- | --- | --- |
| Classical | `T`, `F` for well-formed formulas | handled outside the truth-value set | not represented by the truth values | depends on language and interpretation |
| Three-valued (Łukasiewicz/Kleene) | `T`, `F`, `U` | usually outside the value set | explicit | profile-dependent |
| FDE / Belnap–Dunn | `Neither`, `TrueOnly`, `FalseOnly`, `Both` | support state is separate | explicit/information-based | profile-dependent |
| Onto4 | `T`, `F`, `U`, `C` | explicit canonical verdict `C` | explicit `U` | context/profile-bound |

Onto4 does not claim that classical logic treats arbitrary natural-language
strings as meaningful. For a well-formed proposition under a fixed classical
interpretation, the truth-value space is binary; semantic inadmissibility is
handled before that truth evaluation. Onto4 makes this preliminary semantic
failure explicit as `C`.

## Self-reference and the distinction profile

Self-reference is not automatically a category error. The canonical typed
profile permits ordinary reflexive equality:

```text
a = a -> T
```

An optional historical `DistinctionProfile` explores a narrower philosophical
hypothesis: an operation may require a grounded distinction between its object
and its assessment frame. Under that named profile, an ungrounded self-
application of a semantic operator may yield `C`; this is not the universal rule
`SelfReference => C`.

For the longer philosophical treatment, see:

- [Liar paradox example](docs/examples/liar-paradox.md)
- [Distinction and the liar paradox](docs/distinction-liar-paradox.md)

## Further reading

The repository keeps formal profiles, examples and historical essays separate
from this introduction. Start with the operator tables for executable details,
then select the semantic profile and context relevant to the question being
studied.
