# Onto4
[For the Russian version of this README, see](README-RU.md).

**Onto4** is a context-bound four-valued semantic verdict system. It separates
semantic well-formedness from truth, and it never treats a verdict as evidence
of authority or action permission.

The historical project reference is the [LimiNode/Onto4 repository](https://github.com/LimiNode/Onto4).

The name **Onto4** comes from **"ontology"**—the study of what exists, in what sense, and under what conditions a statement can mean anything.

> Not every assertion has meaning.
> Before discussing whether it is true or false, we must ask:
> **"Can it even be meaningfully formulated?"**

In classical logic any statement is considered either true (`T`) or false (`F`). Yet that system does not distinguish cases where a statement cannot be meaningfully formulated at all or where the logical categories of truth and falsity do not apply.

**Onto4** introduces a more precise classification by adding two additional statuses:

- `U` — **undetermined**: the statement is meaningful, but `T`/`F` is not established in the current context;
- `C` — **category error**: the checked formalization is not well formed in the selected ontology/semantic profile.

Thus Onto4 extends classical logic by introducing the concept of **ontological admissibility** as a preliminary condition for analysis. Each statement is first checked for meaning and evaluability and receives one of four values:

- `T` — **true**: meaningful and true;
- `F` — **false**: meaningful and false;
- `U` — **undetermined**: meaningful but not resolved as true or false;
- `C` — **category error**: rejected by semantic/type/presupposition checking.

### Formal structure of Onto4

Each value in Onto4 is described by a triple of binary features:

| Feature      | Label          | Values        | Description |
|--------------|---------------|---------------|-------------|
| Sense        | `S` (Sensible) | `1` / `0`     | Whether the statement makes sense in this context |
| Evaluability | `E` (Evaluable)| `1` / `0`     | Whether it can be logically judged as true or false |
| Truth value  | `V` (Value)    | `1` / `0` / `–` | True, false or not applicable (if `E = 0`) |

Onto4 feature table:

| Onto4 | `S` | `E` | `V` | Comment |
|-------|-----|-----|-----|------------------------------|
| `T`   | 1   | 1   | 1   | Makes sense, evaluable, and true |
| `F`   | 1   | 1   | 0   | Makes sense, evaluable, and false |
| `U`   | 1   | 0   | –   | Makes sense, but logical evaluation does not apply |
| `C`   | 0   | 0   | –   | Category/type checking rejects the formalization |

> Thus every logical value in Onto4 is not merely a label (`True`/`False`) but a **combination of ontological and logical conditions**.

---

### Relation to classical logic

Onto4 **does not abolish binary logic**, but extends it with an **ontological layer**:

- If `S = 1` and `E = 1`, logic reduces to the classical case;
- If `S = 1` but `E = 0` — logical indeterminacy (`U`);
- If semantic checking fails (`C`), the invalid formalization is not evaluated.

This separation enables **context-sensitive reasoning** where a statement may be rejected not because it is false but because it is inexpressible within the system of concepts.

### Overcoming the observer paradox

Classical logic implicitly relies on a metaphysical assumption of an external, universal observer for whom any statement:

- has a fixed, unambiguous meaning,
- can be formulated in any context,
- and is subject to logical evaluation as true or false.

Such an observer:

- is **outside time** — knowing past, present and future as a whole;
- **outside language and culture** — concepts are always defined;
- **outside the system itself** — merely "looking from the side".

This is not a logically derived entity but a **projection of the subjective feeling "I, observing everything"**, built into thinking by default. In reality such an observer is a **metaphysical fiction** that ignores the limitations of context, language and concepts.

**Onto4** rejects this fiction.

> ❓ *"Is it even possible to formulate this statement meaningfully within the given system—in its language, time, culture?"*

If the answer is no, the checked formalization receives status `C` —
**ontologically inadmissible** — and is excluded from ordinary logical evaluation.

Thus Onto4 allows reasoning **from within the system itself**, acknowledging:

- the limitedness of language,
- the impossibility of a universal context,
- and the dependence of meaning on the participant's viewpoint.

### Examples

```
"2 + 2 = 4"                               → T (meaningful and true)
"An elephant is smaller than an ant"      → F (meaningful and false)
"It will rain tomorrow"                   → U (meaningful but truth not yet determined)
"Mass(integer_7) > 1000 kg"            → C (a typed category error)
"The Internet existed in the year 0 AD"  → F or U, depending on the
                                             historical interpretation and evidence
```

Onto4 is a logic in which truth is secondary:
first comes meaning, then applicability, and only after that—truth or falsity.

### Context and the meaning of a statement

In Onto4 any statement is considered **within a context** that defines:

- which concepts exist at all,
- what language is used,
- what rules are allowed,
- and in what time, culture or mental model the judgment occurs.

Unlike classical logic, Onto4 **does not evaluate a statement "by itself"**—it must first be meaningful within the given context.

This is reflected in the signature of the meaning function:

```text
meaning : Statement × Context → Onto4Value
```

A context `Context` can be represented as a set of parameters:

```text
ContextFrame = {
  Language = Russian,
  Time = 2025,
  Concepts = {internet, computer, falsehood, truth},
  ReferenceMode = SelfReferenceAllowed,
  EvaluationPolicy = StrictMeaningCheck,
  ...
}
```

A context may include any parameters necessary for interpretation, and depending on them the same statement may have different meaning—or none at all.

Example:

```text
S = "The Internet exists"

C₁ = {
  Time = 0,
  Language = Latin,
  Concepts = {aqua, gladius, imperium}
}

C₂ = {
  Time = 2025,
  Language = Russian,
  Concepts = {интернет, компьютер, сеть}
}

meaning(S, C₁) = U   // interpretation/evidence is unresolved in this frame
meaning(S, C₂) = T   // meaningful and true
```

This allows Onto4 to abandon the abstract observer for whom all statements always have sense and value.

Formally, the verdict is context-bound:

```text
V(P | ontology, semantics, epistemics, inference, perspective)
```

A concrete implementation can carry these dimensions explicitly:

```cpp
struct ContextFrame {
    OntologyProfile ontology;
    SemanticProfile semantics;
    EpistemicProfile epistemics;
    InferenceProfile inference;
    Perspective perspective;
};
```

The same text may therefore receive different verdicts under different
`ContextFrame` profiles. A missing object in the current model is not by itself
`C`; the semantic checker must show that the expression is ill typed or its
presupposition is inadmissible.

### Onto4 and Evidence4 are different axes

Onto4 describes semantic status. Evidence is tracked separately in a
Belnap–Dunn-like `Evidence4` space:

```text
Neither | TrueOnly | FalseOnly | Both
```

For example, `Onto4 = U` with `Evidence4 = Neither` means a meaningful claim
without admitted support, while `Onto4 = U` with `Evidence4 = Both` means a
meaningful claim with conflicting support. `Both` is not a category error.

`Sense`/definedness is a property produced by formalization and semantic
checking; it is not required to be an additional logical operator. A checked
formalization should retain its ontology, assumptions, normalized expression,
diagnostics and context revision.

### Canonical strict semantics and determining projections

The canonical Onto4 profile is **strict**: a compound proposition is assessed
as a whole, and a category error in any required operand remains visible:

```text
¬C = C
C ∧ X = C
C ∨ X = C
C → X = C
X → C = C
```

This choice is deliberate. It prevents a true or false branch from silently
erasing an invalid ontology or hidden presupposition, keeps assessment
compositional, and makes proofs, diagnostics, replay and safety review
conservative. Strict semantics answers: *is this complete formal proposition
admissible and what verdict follows from it?*

For example, let `A` be a well-formed claim that a grandfather existed in a
reconstructed past (`A = T`) and let `B` assert an absolute, model-independent
property `WasAbsolutely(grandfather)` that the selected ontology does not
define (`B = C`). The object-level formula `A ∨ B` is `C` under strict
semantics. Returning `T` would hide the invalid second formalization.

An operational **determining/short-circuit projection** can still be useful:
`T ∨ X` may determine a query result without evaluating `X`, and `F ∧ X` may
determine a result without evaluating `X`. That projection belongs to query
resolution, search, decision policy and candidate selection—not to canonical
truth semantics. It must retain the skipped branch, its context and its
diagnostic, and it must never replace the strict result in a proof, audit or
replay.

The same distinction applies to alternative formalizations. If candidates are
`F1 -> T` (causal continuity) and `F2 -> C` (an undefined persistent-substance
predicate), a meta-level query may report *at least one admissible
formalization* and continue with `F1`. It must not encode that selection as the
object-level formula `F1 ∨ F2`, because strict Onto4 would correctly return
`C` for that malformed compound.

A second example is identity across time. A relation such as
`Continuity(me_child, me_now)` may be `T`, while a stronger predicate
`SamePersistentSubstance(me_child, me_now)` may be `C` because the selected
ontology has no persistent-substance category. Strict evaluation keeps that
distinction visible; a determining query may still select the valid relational
formalization without asserting the undefined one.

---

## Comparison of Onto4 with other logics

| Logic | Values | Support for meaningless expressions | Indeterminacy | Self-reference | Features |
|-------|--------|------------------------------------|---------------|----------------|----------|
| **Classical logic** | T, F | ❌ | ❌ | paradox | Simple but inflexible. Everything is meaningful and evaluable. |
| **Three-valued (Łukasiewicz, Kleene)** | T, F, U | ❌ | ✅ | paradox | Introduces "unknown" but still requires meaning |
| **FDE / paraconsistent logic** | T, F, {T∧F} | ❌ | ✅ | paradox | Allows contradictions without collapse |
| **Modal logic** | T, F across worlds | ❌ | ◼ | paradox | Extends classical logic via modalities |
| **Onto4** | T, F, U, C | ✅ | ✅ | context-bound | Checks semantic admissibility before truth assessment and separates meaning from truth |

### Examples and philosophical analyses

Onto4 is a tool for analyzing philosophical and linguistic paradoxes that are hard to express in classical systems.

The project includes discussions of cases such as:

- **The liar paradox** — why the phrase *"This statement is false"* has no meaning in Onto4:
  📄 [docs/examples/liar-paradox.md](docs/examples/liar-paradox.md)
- **On distinction and the liar paradox** — how deconstructing the “observer” dissolves the paradox:
  📄 [docs/distinction-liar-paradox.md](docs/distinction-liar-paradox.md)

---

### Tables of logical operators

The operator tables are currently a **draft profile**. In particular, the
strict treatment of `C`, implication and equivalence must be kept consistent
with the chosen definitions and tested algebraic properties.

For details, see the tables of logical operators:

📄 [docs/truth-tables.md](docs/truth-tables.md)

The repository's draft tables are not an Evidence4 table and do not define
authority, provider admission or physical effects.
