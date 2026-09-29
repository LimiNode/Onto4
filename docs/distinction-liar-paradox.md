# Distinction and the liar paradox (historical essay)

This document records a philosophical motivation that can be selected as an
optional `DistinctionProfile`. It is not a claim that classical logic requires
an external observer, and it is not the canonical Onto4 rule for self-reference.

## Distinction as a modelling choice

The profile studies systems in which a comparison is meaningful only when its
operands are distinct:

```text
compare : Object × Object -> Verdict
meaningful(compare(a, b)) iff a != b
```

This can be useful when the subject of analysis is a process, a transition or
an information difference rather than an object treated in isolation. It is a
semantic restriction of that profile, not a theorem about all logics.

## Liar analysis under the profile

For:

```text
L := "This statement is false"
```

the profile formalizes the self-application as `compare(L, L)`. Since the
profile rejects identical operands, the formalization receives `C` with a
diagnostic identifying the `DistinctionProfile` rule. The conclusion is
profile-relative: another `SemanticProfile` may admit a typed truth predicate
and analyse the fixed point differently.

## Observer language

The original essay used an “observer” metaphor to discuss how a comparison can
be represented. That metaphor is explanatory only. Distinction may be an
internal relation or state transition; it does not require a metaphysical
universal observer. The useful engineering lesson is to make the semantic
profile, reference relation and admissibility rule explicit instead of assuming
them globally.

## Information perspective

Information and comparison often involve alternatives or distinguishable
states. This motivates checking the domain and relation before assigning a
verdict, but it does not imply that every reflexive formula such as `a = a` is
meaningless. The optional profile must therefore remain separate from the
canonical typed Onto4 profile.
