# The liar paradox in Onto4

This example starts with the familiar idea and only then introduces the
profile terminology. The purpose is to show why a self-referential sentence can
be difficult without making self-reference a universal category error.

## The intuitive paradox

Consider the sentence:

```text
L := "This statement is false"
```

If `L` is true, what it says makes it false. If `L` is false, what it says
appears to make it true. The sentence turns its own truth assessment into part
of the condition being assessed, producing the familiar liar paradox.

## What the canonical profile says

Onto4 does not treat every self-reference as meaningless. In the canonical
typed profile:

```text
a = a                         -> T
SelfReference(a)              -> T, F or U depending on the predicate/context
```

The liar becomes a formal expression only after the profile specifies a typed
truth predicate, its domain and a policy for fixed points:

```text
L := ¬Truth(L)
```

If those semantic contracts admit the construction, the selected profile's
logic handles the result. The sentence is not converted to `C` merely because
it refers to itself. `C` requires a concrete failure of semantic admissibility,
such as an undefined argument type or an explicit prohibition on this
self-application.

## Why distinction was proposed

The repository's earlier philosophical interpretation asked for a distinction
between the thing being assessed and the frame that assesses it. A distinction
can be represented by two roles or representations of one object:

```text
             comparison frame
              /           \\
          r1(x)           r2(x)
```

Even when we write a reflexive expression such as `a = a`, a comparison can
still involve two distinguishable positions or two representations of one
referent. The referent may be one object; the roles in the relation are what
make the assessment possible.

The “observer” in this explanation is not necessarily a person or a
metaphysical subject. It is a name for the relational position, model or frame
that makes the comparison possible.

Start with a relation:

```text
D(a, b)                         -- distinction between two relata
```

When the comparison frame is reified as an ordinary object, the language can
apply it to its own representation:

```text
relation / frame -> reification -> object O -> O(O)
```

This is one way self-reference can arise. The question is whether the required
grounding survived the transition from a meta-level frame to an object-level
term.

## Where grounding fails in the liar

In an ordinary assessment there is a distinction between the proposition `P`
and the frame that establishes its truth status:

```text
assessment_frame --assesses--> P
```

For the liar:

```text
L := ¬Truth(L)
```

the value of `L` depends on `Truth(L)`, while `Truth(L)` in turn requires the
truth status of `L`:

```text
L
└─ depends on ¬Truth(L)
               └─ depends on the truth status of L
```

The result is a closed chain in which the outcome of the assessment is used as
the basis for that same assessment. `DistinctionProfile` interprets this
specific ungrounded dependence of a semantic operator as a violation of its
applicability condition:

```text
UngroundedSelfApplication(Truth, L)
    -> C
```

This does not make every recursive definition or every self-reference
meaningless. `C` appears here only because the selected profile requires an
independent grounding for truth assessment.

## The optional distinction profile

The historical `DistinctionProfile` makes that grounding requirement explicit.
It can classify the liar as follows:

```text
unfounded self-grounding
    -> semantic admissibility failure
    -> C
```

This is a profile-relative diagnosis. It is not the universal rule
`SelfReference => C`; the narrower idea is:

```text
UngroundedSelfApplication(semantic_operator) => C
```

when the selected profile requires a distinction that the formalization cannot
provide. The profile must be named in the context and must not be confused with
the canonical typed Onto4 semantics.

The liar is useful in this profile not because it “breaks logic”, but because it
makes the boundary of a semantic construction visible. While an operator works,
its preconditions can remain unnoticed. The self-referential failure forces the
question: was the truth operator admissible in this context at all?

This is the broader Onto4 lesson: sometimes the problem is not choosing between
`T` and `F`, but that the assessment operation itself has lost its meaning in
the selected context.

For the longer philosophical motivation, see [Distinction and the liar
paradox](../distinction-liar-paradox.md).
