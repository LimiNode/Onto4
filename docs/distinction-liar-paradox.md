# Distinction and the liar paradox: a philosophical interpretation

The liar paradox is usually stated as:

> “This statement is false.”

Let this statement be `L`:

```text
L := "This statement is false"
```

or, more formally:

```text
L := ¬Truth(L)
```

If `L` is true, then its own content says that it is false. If `L` is false,
then what it says appears to be true. This creates a closed dependency:

```text
L -> Truth(L) -> L
```

The example is usually treated as a problem of self-reference and the truth
predicate. Here we approach it differently: through **distinction** and the
conditions that make logical assessment meaningful in the first place.

This is not a universal theory of self-reference, nor a claim that every liar
construction must receive the same answer. Onto4 models this approach as a
separate **distinction profile** (`DistinctionProfile`).

## Difference and knowledge of difference

Begin with a simple intuition. To call something true or false is to
distinguish at least two possibilities:

```text
true / false
```

Comparing system states likewise presupposes a difference:

```text
state A / state B
```

Yet a difference between two objects and knowledge of that difference are not
the same thing. Suppose two objects exist:

```text
A
B
```

They may be different in reality:

```text
A != B
```

Their mere existence, however, does not create a separate item of information
that says “`A` differs from `B`.” For the difference to be present in a system
as a represented relation, record or item of knowledge, it needs a carrier:

```text
C := Distinguishes(A, B)
```

The separation can be written as:

```text
difference in reality:     A != B
represented difference:   C := Encode(A != B)
```

`C` is a third element structurally, but not necessarily a third physical
object. It may be a relation, system state, record, rule, event or any other
structure in which the difference is represented. Even mathematical
`R(A, B)` introduces the relation `R` into the description; knowledge of the
difference is not extracted from `A` and `B` alone.

Only a represented difference can participate in further reasoning. Onto4 is
concerned not only with whether objects differ in reality, but also with
whether the selected context provides an admissible carrier for the relation
required by an assessment.

## What “observer” means here

Here the word **observer** denotes a carrier of represented distinction. It
does not necessarily mean a person, a mind or an external metaphysical
subject.

If a person knows that Vasya and Petya are different people, the description
contains not only:

```text
Vasya
Petya
```

but also a distinct informational state:

```text
K := "Vasya != Petya"
```

It is `K` that carries the knowledge of their difference. The same role may be
played by a database, a sensor, a comparison rule or an internal state of an
automated system.

In this model, therefore, an observer is a special image of a more general
notion: a **carrier of distinction**. It may be internal to the system under
consideration and has no privileged point of view.

This qualification matters for processes as well. States `A` and `B` need not
themselves carry information about a transition between them. That information
is carried by a represented transition structure:

```text
A
B
T := Transition(A, B)
```

Here it is `T` that records the transition and thus makes the difference
between `A` and `B` available to reasoning.

## Distinction does not prohibit reflexivity

Requiring a carrier of distinction does not mean that every relation must join
two different physical objects. In:

```text
a = a
```

the referent is the same, but the formula contains two distinguishable
argument positions, and the equality relation represents their comparison:

```text
left position:   a
right position:  a
relation:        Equal(a, a)
```

Ordinary reflexive equality is therefore meaningful:

```text
a = a -> T
```

The distinction profile does not introduce a rule such as:

```text
SelfReference(x) -> C
```

It does not make every reflexive relation, recursion or repeated reference to
one object meaningless. Its question is more precise: **does this particular
assessment have the independent carrier and basis that its operation
requires?**

## From a relation to an object of reasoning

Suppose a representation of difference is given by:

```text
C := Distinguishes(A, B)
```

A formal language may then make `C` itself an object of reasoning. We can ask
where `C` came from, compare it with another record, or assess its truth. This
new assessment must itself be represented somewhere:

```text
D := Assess(C)
```

This produces distinct levels:

```text
A, B                         -- objects being distinguished
C := Distinguishes(A, B)     -- carrier of the distinction
D := Assess(C)               -- carrier of the assessment of C
```

This is not an infinite regress for every practical item of knowledge. Within
a domain, a system may accept records, rules and observations as its given
basis. Levels become problematic when an operation must create its own basis
solely from its own result.

Syntax may permit self-application:

```text
Assess(Assess)
Distinguishes(C, C)
Truth(Truth(...))
```

The ability to write an expression does not guarantee its semantic
admissibility. For every operator, the remaining question is whether the
carrier of the relation and the basis required for its application have been
preserved.

## Object level and assessment level

An ordinary assessment distinguishes a proposition from the represented state
of its assessment:

```text
P                         -- proposition being assessed
E := AssessTruth(P)       -- carrier of its truth assessment
```

`E` may depend on term denotations, inference rules, observations or other
grounds supplied by the semantic profile. Schematically:

```text
assessment basis
       |
       v
E := AssessTruth(P)
       |
       v
     T / F
```

The proposition under assessment and the carrier of its assessment play
different roles. This does not require an external omniscient subject; `E` may
be an internal evaluator state. What matters is that the result does not
replace the whole basis that is supposed to produce that same result.

Some formal systems explicitly define rules for recursive definitions, fixed
points or self-referential predicates. A closed dependency may have an
admissible semantics in such systems. The distinction profile does not deny
that possibility. It requires the relevant rule to be stated and to provide a
basis for the assessment.

## Information as represented distinction

The same intuition appears in information theory. A bit is meaningful because
two states are possible:

```text
0 / 1
```

The existence of two abstract possibilities does not yet tell a system which
state is realized. That requires a physical or symbolic structure carrying the
selected value: a signal level, memory cell, record or some other state.

It is therefore useful to distinguish:

```text
possibility of difference
representation of difference
use of that representation in assessment
```

This is not a proof of a particular logical system. It is a philosophical
motivation: before assigning a truth verdict, one should ask whether the
represented relations and grounds needed to make the assessment meaningful
are available. Onto4 can express the absence of those conditions with the
separate verdict `C`.

## Applying the profile to the liar

Return to:

```text
L := ¬Truth(L)
```

Determining the value of `L` requires a truth assessment:

```text
E := AssessTruth(L)
```

But the content of `L` is already defined as the negation of that very
assessment. This creates a closed dependency:

```text
L -> E -> L
```

or, in the original notation:

```text
L -> Truth(L) -> L
```

In an ordinary case, `E` represents the assessment of a proposition `P` from
rules and data that do not reduce to first demanding the result of the same
assessment. In the liar, the carrier of assessment and the assessed content
close over one another:

```text
        +----------------+
        |                |
        v                |
L := ¬Truth(L)           |
        |                |
        +-> E := AssessTruth(L)
```

The problem is not that `L` mentions itself as text. It is not a ban on all
recursion or an impossibility of reflexive relations. In this profile, the
problem is the **collapse of the assessed object and the independent carrier
of the basis required by the truth operator**.

This condition can be named:

```text
UngroundedSelfApplication(Truth, L)
```

If the selected profile requires an independent basis for `Truth` and supplies
no separate fixed-point rule, the construction fails semantic admissibility:

```text
UngroundedSelfApplication(Truth, L) -> C
```

## Why the result is `C`, not `U`

`U` means that a proposition is semantically admissible but that no definite
`T/F` verdict has yet been established. The system may, for example, lack
observations or proof.

For the liar as analysed here, the problem occurs earlier. It is not merely
that the value of `Truth(L)` is unknown: the proposed way to determine it
already requires the result of that same assessment. The question is therefore
not:

```text
which answer should be selected: T or F?
```

but:

```text
is Truth admissible on this basis?
```

`DistinctionProfile` answers no and returns `C`: a category error for this
operation in this context.

## This is not a universal prohibition of self-reference

The analysis does not imply the universal rule:

```text
SelfReference(x) -> C
```

A self-referential expression can be meaningful. Reflexive equality `a = a`
receives `T` when its terms are admissible. A recursive definition may have a
basis and a termination rule. Fixed-point theory may provide special semantics
for some closed formulas.

The more precise rule of the distinction profile is:

```text
UngroundedSelfApplication(semantic_operator, expression) -> C
```

It applies only when the selected operator requires an independent carrier of
its basis, while the construction collapses that carrier into its own result
and supplies no other admissible rule.

That is why this interpretation is a separate semantic profile rather than a
universal law of Onto4. Another profile may type the truth predicate
differently, stratify language levels, or provide a fixed point.

## The paradox as a boundary detector

On this interpretation, the liar is interesting not because it “breaks
logic,” but because it exposes presuppositions that remain hidden in ordinary
reasoning.

When a truth operator is applied to propositions with an accepted basis, we
rarely ask why its application is admissible. Self-reference forces the
question into view. Failure becomes diagnostic: it reveals a boundary of the
selected operation and profile.

What first appeared to be a choice between:

```text
T
F
```

becomes a higher-level question:

```text
is the assessment operation itself meaningful in this construction?
```

Onto4 has the separate verdict `C` precisely to distinguish an unknown answer
from an inadmissible question.

## Conclusion

The distinction profile begins by separating reality from its representation:

```text
A != B                         -- the objects differ
C := Encode(A != B)            -- the difference is represented
```

A represented distinction needs a carrier. That carrier need not be a person,
a mind or a separate physical object; it can be a relation, record, state,
transition or rule. “Observer” is only a convenient image for such a carrier,
not a privileged external subject.

When a carrier of assessment becomes an object in the language, self-reference
becomes possible. Syntactic possibility, however, does not guarantee that the
conditions required by the semantic operator remain available.

For the liar:

```text
L := ¬Truth(L)
E := AssessTruth(L)
L -> E -> L
```

the assessment closes over its own result without an independent basis. If the
selected profile requires such a basis and provides no other rule for the
closed dependency, the formalization receives `C`—not because it has been
proved false, and not because the answer is merely unknown, but because the
assessment operation itself has lost its semantic support in this
construction.

This is the broader lesson of the example for Onto4:

> Sometimes the problem lies not in the answer, but in the conditions that
> were supposed to make the question meaningful.
