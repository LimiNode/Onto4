# Onto4

[Русская версия](README-RU.md)

**Onto4** is a context-dependent four-valued logic in which a proposition is
checked for semantic admissibility before its truth value is assessed.

The name **Onto4** comes from **ontology**: the study of *what exists*, *in
what sense it exists*, and *which categories and relations are available when
we describe the world*.

The central idea of Onto4 is simple:

> Not every reasoning error comes from choosing the wrong answer. Sometimes the
> conceptual space in which the question was asked is itself inappropriate.

Ordinary reasoning usually asks:

- Is it true?
- Is it false?
- Or do we not know yet?

But there is an earlier question:

> **Can the proposition itself be meaningfully formulated within the adopted
> ontology and semantics?**

For example, one may ask where the past is “now”, or whether exactly the same
self persists through time, without noticing that words such as `where`, `past`,
or `the same self` already presuppose a particular ontology.

Onto4 makes this hidden assumption part of the logical assessment itself.

## Ontological admissibility

Onto4 does not discard ordinary truth and falsity. It adds a prior check:

> **Is this proposition admissible in the selected conceptual framework?**

If the formulation is meaningful, it can then be assessed as true, false, or
unresolved.

If the formulation itself relies on a category, relation or presupposition that
does not apply in the selected context, Onto4 returns a separate verdict: `C`.

Conceptually:

```text
Is the formulation meaningful?
        |
        +-- no  -> C
        |
        `-- yes
             |
             +-- is T/F determined? -- no -> U
             |
             +-- true --------------------> T
             |
             `-- false -------------------> F
```

This yields four verdicts:

| Verdict | Meaning |
|---|---|
| `T` | the proposition is meaningful and true in the selected context |
| `F` | the proposition is meaningful and false |
| `U` | the proposition is meaningful, but no determinate `T/F` verdict has been established |
| `C` | the selected formulation has no valid interpretation in the current ontology or semantics |

The key distinction is:

```text
U: the question makes sense, but its answer is unresolved.

C: the problem may lie in the question itself or in the categories
   used to formulate it.
```

`C` does not mean that an object simply does not exist, and it is not a stronger
form of `F`.

For example:

```text
UnicornExists() -> F
```

can be an ordinary false proposition if the concept of a unicorn is properly
defined.

By contrast:

```text
Mass(integer_7)
```

with

```text
Mass : PhysicalObject -> MassValue
integer_7 : Integer
```

receives `C`, because the predicate does not apply to that sort of object.

## Formal structure

The four states can be described using three features:

| Feature | Symbol | Values | Meaning |
|---|---|---|---|
| Semantic sense | `S` (Sensible) | `1 / 0` | whether the formulation has an admissible meaning in this context |
| Determination | `D` (Determinate) | `1 / 0` | whether a definite `T/F` verdict has been established |
| Truth value | `V` (Value) | `1 / 0 / –` | true, false, or not applicable |

Thus:

| Onto4 | `S` | `D` | `V` | Meaning |
|---|---:|---:|---:|---|
| `T` | 1 | 1 | 1 | meaningful and true |
| `F` | 1 | 1 | 0 | meaningful and false |
| `U` | 1 | 0 | – | meaningful, but `T/F` is unresolved |
| `C` | 0 | – | – | the formulation is semantically inadmissible |

> An Onto4 verdict is therefore not merely another label beside `True` and
> `False`. It combines semantic admissibility with logical assessment.

An early version of Onto4 used `E` (`Evaluable`) instead of `D`. That wording
proved ambiguous: a meaningful proposition may be perfectly evaluable in
principle while its actual truth value is still unresolved. The current
formulation therefore uses `D` for determination.

## Context

An Onto4 verdict belongs not to an isolated text string but to a **proposition in
context**.

Conceptually:

```text
V(P | ontology, semantics, epistemics, inference, perspective)
```

A context may determine:

- which entities and categories exist in the model;
- which predicates apply to which entities;
- how terms and symbols are interpreted;
- which presuppositions are admissible;
- which evidence is available;
- from which perspective the assessment is made.

The same natural-language sentence can therefore receive different verdicts
under different formalizations.

## Example: time

Consider:

> “My grandfather really was.”

One possible formulation interprets `was` relationally:

```text
ExistsAt(grandfather, t)
EarlierThan(t, now)
```

This is meaningful and may receive `T`, `F`, or `U`.

But another interpretation may implicitly ask for a stronger property:

```text
WasAbsolutely(grandfather)
```

as though past existence were an absolute, model-independent mode of being.

If the selected ontology contains no such property, the result is not `F` but
`C`.

This does not mean:

> “My grandfather did not exist.”

It means:

> “This way of formulating the question has no interpretation in the selected
> model of time.”

Meaning returns once the relation is made explicit:

```text
existed earlier relative to the current state
```

rather than treating “was” as an absolute property of an object.

## Example: identity

Likewise, consider:

> “Am I now the same self that I was as a child?”

If identity is defined through a continuity relation:

```text
Continuity(me_child, me_now)
```

the proposition is meaningful and may receive `T`, `F`, or `U`.

But a stronger formulation:

```text
SamePersistentSubstance(me_child, me_now)
```

assumes a separate persistent entity that remains numerically identical through
time.

If the selected ontology models memory, bodily states, experience and causal
continuity but contains no such persistent substance, this formulation receives
`C`.

Again, the problem lies not in answering yes or no, but in a category silently
introduced by the question.

This is the main purpose of Onto4's fourth verdict:

> **It allows a reasoning system to question not only an answer, but also the
> conceptual space in which the answer is being sought.**

## `C` and `U`

It is important not to conflate `C` with `U`.

`U` means:

```text
the formulation is meaningful;
a determinate T/F verdict has not been established.
```

Possible reasons include insufficient evidence, conflicting evidence,
computational limits or model indeterminacy. `C` means something different:

```text
the selected formulation itself fails semantic admissibility.
```

Missing information about the mass of a car gives `U`. Asking for the mass of
the number seven gives `C`.

## Onto4 and Belnap–Dunn

Evidence state is a separate question. For that purpose one can use a
Belnap–Dunn-style four-state structure:

```text
Neither    — support for neither polarity
TrueOnly   — support for truth
FalseOnly  — support for falsity
Both       — support for both
```

This axis does not replace Onto4. For example, `Onto4 = U` with
`Evidence = Neither` and `Onto4 = U` with `Evidence = Both` describe different
epistemic situations while the proposition can remain meaningful in both cases.

Belnap–Dunn asks: *what support exists for and against the proposition?*
Onto4 asks: *what is the semantic and logical status of the formulation itself?*

## Canonical operator semantics

For object-level formulas Onto4 uses **strict semantics**. If a required part of
a compound formula has value `C`, the canonical result is also `C`:

```text
¬C = C

C ∧ X = C
C ∨ X = C

C → X = C
X → C = C
```

The reason is that a true or false neighbouring branch must not hide a category
error elsewhere in the formula. For example, if `A = T` and `B = C`, then
`A ∨ B = C` under canonical Onto4 semantics.

An implementation may still use short-circuit evaluation (`T ∨ X -> T`,
`F ∧ X -> F`) as an operational optimisation, but that projection does not
replace the canonical assessment of the whole formula.

Complete operator tables:

- [English operator tables](docs/truth-tables.md)
- [Russian operator tables](docs/truth-tables-ru.md)

## Relation to classical logic

Onto4 does not claim that classical logic treats every arbitrary natural-language
string as meaningful. Once a language, interpretation and well-formed formula
are fixed, classical truth evaluation is normally binary:

```text
T / F
```

Onto4 makes semantic admissibility of the formulation an explicit part of the
reasoning result:

```text
meaning / applicability
        ↓
truth evaluation
```

## Self-reference

Self-reference does not automatically imply `C`:

```text
a = a -> T
```

The project also preserves a historical **DistinctionProfile**, a separate
philosophical model that explores distinction, the external frame of assessment
and self-application of semantic operators. Under that profile some forms of
ungrounded self-reference may receive `C`, but this is not a universal Onto4
law.

See:

- [Liar paradox](docs/examples/liar-paradox.md)
- [Distinction and the liar paradox](docs/distinction-liar-paradox.md)

## In short

```text
T — the question makes sense; the answer is yes.
F — the question makes sense; the answer is no.
U — the question makes sense; the answer is unresolved.
C — the problem may lie in the question itself.
```

The purpose of Onto4 is to make hidden ontological assumptions visible and to
give a reasoning system a way to detect when continuing to search for an answer
inside the chosen categories may itself be a mistake.
