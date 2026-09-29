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

## Contextual distinction

Begin with a simple intuition. To call something true or false is to
distinguish at least two possibilities:

```text
true / false
```

Comparing system states likewise presupposes a difference:

```text
state A / state B
```

But we should not turn distinction into a ready-made property of a pair of
objects. Let two states be denoted by `A` and `B`. The existence of two labels
alone does not establish an absolute, context-independent fact `A != B`. Before
an act of distinction, that expression is a hypothesis of a language or model
about a possible relation.

Distinction arises in an act, relation or system state:

```text
A
B

D(A, B | K)
```

Here `K` is the context of distinction: a physical interaction, measurement,
computational state, memory, model or linguistic scheme. In an ontology where
measurement or collapse is treated as a physical event, one might write:

```text
D_physical(A, B)
```

This is not a claim about a particular interpretation of quantum mechanics. It
is an example of a possible physical ontology of distinction. The same event
may later be represented in another system:

```text
D_cognitive(A, B)
```

`D_cognitive` need not be identical to `D_physical`: it may arise later, be
incomplete, mistaken or absent altogether. In both cases, distinction belongs
to a context, process or carrier; it is not knowledge that appears “from
nowhere”.

This can be written as:

```text
D(A, B | K)
```

Yet a physical act of distinction and its representation for another part of
the system are still not the same thing. For a distinction to be stored or
available as knowledge, the system needs a corresponding carrier:

```text
R := Represents(D(A, B | K))
```

`R` is a third element structurally, but not necessarily a third physical
object. It may be a relation, system state, record, rule, event or another
structure in which distinction is represented. `D` itself may be a physical
event or state; the additional `R` is needed when another part of the system
must retain or use it as knowledge.

Onto4 asks whether the selected context provides an admissible act and carrier
for the relation required by an assessment.

## What “observer” means here

Here the word **observer** denotes one possible context or carrier of
represented distinction. It does not necessarily mean a person, a mind or an
external metaphysical subject.

If a person knows that Vasya and Petya are different people, the description
contains not only:

```text
Vasya
Petya
```

but also a distinct informational state:

```text
R_V := "Vasya != Petya"
```

`R_V` carries knowledge of their difference in some context `K`. A physical
interaction may itself realize the act of distinction `D`, while a sensor,
memory or database may retain its result:

```text
D(A, B | physical_interaction)
R_sensor := Represents(D(...))
R_memory := Represents(D(...))
R_database := Represents(D(...))
```

In this model, therefore, an observer is a special image of a more general
notion: a **context and carrier of distinction**. It may be internal to the
system under consideration and has no privileged point of view. The model does
not assume a real view “outside all reality”.

This qualification matters for processes as well. States `A` and `B` need not
themselves carry information about a transition between them. That information
is carried by a represented transition structure:

```text
A
B
T := Transition(A, B | K)
R_T := Represents(T)
```

`T` itself may be the physical transition. If another part of the system must
know about it, its result is retained in `R_T`; that record makes the transition
between `A` and `B` available to further reasoning.

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
R := Represents(D(A, B | K))
```

A formal language may then make `R` itself an object of reasoning. We can ask
where `R` came from, compare it with another record, or assess its truth. This
new assessment must itself be represented somewhere:

```text
E_R := Assess(R)
```

This produces distinct levels:

```text
A, B                         -- objects being distinguished
D(A, B | K)                  -- act of distinction
R := Represents(D(A, B | K)) -- carrier of the representation
E_R := Assess(R)             -- carrier of the assessment of R
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

The same intuition appears in information theory. In an ordinary bit model, we
specify two distinguishable states:

```text
0 / 1
```

But even this distinction belongs to the selected descriptive model; it should
not be silently treated as a property of the object “in itself”. The existence
of two abstract possibilities does not yet tell a system which state is
realized. That requires a physical or symbolic structure carrying the selected
state: a signal level, memory cell, record or another relation.

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

## The one-bit world and the outside view

The thought experiment [“One-bit world”](thought-experiments/one-bit-world.md)
helps make this intuition concrete. Imagine an ontology in which only one bit
`b` is given:

```text
b ∈ {0, 1}
```

We normally write immediately:

```text
b(t0) = 0
b(t1) = 1
```

But this has already introduced time, memory and order `t0 < t1`, none of which
was present in the stipulation. In fact, the observer has two of its own states:

```text
N0 := “observed 0”
N1 := “observed 1”
D(N0, N1 | K_observer)
```

The statement “the one-bit world changed” is an interpretation of the
difference between `N0` and `N1`. It may be reasonable in an extended system,
but it does not follow automatically from the bit's state alone.

For an internal claim `Changed(b)` to be meaningful, the ontology must provide
two distinguishable states, an order between them, a carrier of that order and
a criterion that both belong to one object. If all of this belongs only to the
observer, the question concerns the system “bit plus observer”, not the bit by
itself.

The contextual form is therefore:

```text
Changed(b | K)
```

rather than context-free `Changed(b)`. If `Changed(b)` is declared to be a
question about a world containing only `b`, the observer's structure has been
imported into that world. In the selected ontology this may yield:

```text
Changed(b) -> C
```

The separate note develops this deconstruction in full.

## The ideal flash drive and physical meaning

The second thought experiment is [“The ideal flash drive”](thought-experiments/ideal-flash-drive.md).
Its premise is stronger than ordinary file storage: information is fully
identical with the carrier's physical state. If we perform:

```text
Write(brick)
```

the drive does not contain a description of a brick; it literally becomes a
brick:

```text
Flash == Brick
```

If a recorded brick and an ordinary brick are physically indistinguishable, the
statement “this brick was produced by writing” is not contained in the brick
itself. It requires an additional physical carrier `M`. The same happens when
the same state is written again:

```text
S0 = Brick
Write(Brick)
S1 = Brick
```

Without a counter or history, zero, one and a thousand writes cannot be
distinguished. But a counter would again be additional physical state. The
experiment therefore shows that meaning, history and the fact of an operation
do not exist beyond the states and relations in which they are represented.

The more familiar regress of complete self-representation remains a consequence:

```text
F -> F'
Encode(F) != Encode(F')
```

but it is not the primary subject. First we must establish where the physical
distinction that makes a write a write is located. Only then should we turn to
the liar and ask whether an independent context exists for `Truth(L)`.

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
D(A, B | K)                    -- distinction in context K
R := Encode(D(A, B | K))       -- the distinction is represented
```

A distinction belongs to a concrete act, process or system state, and a
represented distinction needs a carrier. That carrier need not be a person, a
mind or a separate physical object; it can be a relation, record, state,
transition or rule. “Observer” is only a convenient image for such a context
and carrier, not a privileged external subject.

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

## Related ideas and research

This interpretation is not derived from the works below, nor does it claim
that they prove `DistinctionProfile`. They are related lines of thought that
help clarify the limits of the analogy:

- G. Spencer-Brown, *Laws of Form* (1969)
  treats distinction as an act of drawing a boundary. This is a close
  motivation, not Onto4's ready-made semantics.
- [Charles S. Peirce: semiotics](https://plato.stanford.edu/entries/peirce/)
  connects a sign's meaning with an object and an interpretant, which resonates
  with the distinction between a carrier's state and its meaning.
- [Alfred Tarski, *The Semantic Conception of Truth*](https://doi.org/10.2307/2102968)
  and the formal tradition that followed show why object-language and
  metalanguage levels matter for a truth predicate. `DistinctionProfile` does
  not replace this analysis; it offers a different, ontologically motivated
  diagnosis.
- [Carlo Rovelli, *Relational Quantum Mechanics*](https://doi.org/10.1007/BF02302261)
  and [Thomas Breuer, *The Impossibility of Accurate State Self-Measurements*](https://doi.org/10.1086/289852)
  provide physical parallels for contextual values and limits on
  self-measurement. They are not proofs of Onto4's philosophical conclusions.

The detailed thought experiments supporting this essay are separate:
[“One-bit world”](thought-experiments/one-bit-world.md) and
[“The ideal flash drive”](thought-experiments/ideal-flash-drive.md).
