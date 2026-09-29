# The liar paradox in Onto4

Consider the sentence:

```text
L := "This statement is false"
```

If `L` is true, its own content says that it is false. If `L` is false, what it
says appears to be true. This creates a closed dependency:

```text
L -> Truth(L) -> L
```

For the longer philosophical account of distinction, representation and
self-reference, see [Distinction and the liar paradox](../distinction-liar-paradox.md).

## Distinction and truth assessment

For `true` and `false` to carry information, the assessment must distinguish at
least two alternatives:

```text
true / false
```

The assessment also normally distinguishes what is being assessed from the
basis on which its result is established:

```text
assessment basis
      |
      v
      P
      |
      v
   T or F
```

The result is not its own basis.

## What goes wrong in the liar

Write the liar using a truth predicate:

```text
L := ¬Truth(L)
```

To determine `L`, we need `Truth(L)`. But to establish `Truth(L)`, we already
need the truth status of `L`:

```text
L
└─ depends on ¬Truth(L)
               └─ depends on the truth status of L
```

No independent assessment basis appears in this chain. The outcome of the
assessment is used as the basis for that same assessment.

## The Onto4 verdict under DistinctionProfile

In a semantic profile that requires an independent basis for truth assessment,
this is not merely an unresolved answer `U`. It is a failure of the truth
predicate's applicability condition:

```text
UngroundedSelfApplication(Truth, L) -> C
```

Here `C` means that the question “is `L` true?” was formulated using an
operation whose conditions are not satisfied in this construction. The problem
lies in the assessment itself, not in missing evidence for either `T` or `F`.

Onto4 calls this semantic profile **DistinctionProfile**.

## Important limitation

This does **not** mean that all self-reference is meaningless. For example:

```text
a = a -> T
```

is an ordinary reflexive formula, and many self-referential constructions are
meaningful. The universal rule

```text
SelfReference(x) -> C
```

is therefore incorrect. The narrower, profile-relative rule is:

```text
UngroundedSelfApplication(semantic_operator) -> C
```

and it applies only when the selected semantic profile requires independent
grounding for that operation.

In this interpretation, the liar is interesting not because it “breaks logic”,
but because it exposes a boundary of the selected semantic apparatus. Sometimes
the problem is not choosing between `T` and `F`; the assessment operation itself
has lost its admissible meaning in the chosen context.

This note presents only the logical path through the example. The roles of an
external position, multiple representations, information as distinction and
reification of the meta-level are discussed in [the longer philosophical
essay](../distinction-liar-paradox.md).
