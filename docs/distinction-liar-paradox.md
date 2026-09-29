# Distinction and the liar paradox (historical essay)

This essay records the philosophical motivation for an optional
`DistinctionProfile`. It is intentionally richer than the short technical
example in `docs/examples/liar-paradox.md`, but it is not a universal law of
Onto4 or a claim that classical logic requires a metaphysical observer.

## Distinction as a condition of a logical state

A logical state is normally assigned through a relation between distinguishable
roles, states or representations. A useful abstraction is:

```text
D(a, b)                    -- a distinction between two relata
state = assess(r1(x), r2(x), frame)
```

The two relata may be different objects, two moments of one process, or two
representations of one object in a comparison system:

```text
object x
   |-- representation r1(x)
   |-- representation r2(x)
             |
             +-- distinction / comparison frame
```

The canonical typed Onto4 profile still permits ordinary reflexive equality:
`a = a -> T` when its terms are well formed. `DistinctionProfile` asks a
different question: whether the semantic grounding of a comparison has
distinguishable roles or representations. It therefore does not reject every
reflexive formula; it rejects an operation whose required grounding is absent.

## The external position and the observer concept

The original essay used an “observer” to name the second position from which a
state, relation or representation can be compared. This does not require a
separate metaphysical subject. The observer can be:

- a second representation of the same object;
- an earlier or later state of a process;
- an internal relation or evaluation frame;
- a model that records the comparison boundary.

The word *observer* is useful because it makes the second position explicit.
The philosophical risk begins when that relational frame is reified as a
universal operator that is presumed to compare anything, including itself.

## Information perspective

Information and comparison involve alternatives or distinguishable states. A
single bit is meaningful relative to the distinction between `0` and `1`; a
process state is meaningful relative to transitions or other states. This
motivates checking the domain, relation and frame before assigning a verdict.
It does not imply that every reflexive formula is meaningless or that an
external observer must exist outside the system.

## Reification and the emergence of self-reference

Begin with a relation:

```text
D(a, b)                         -- distinction of two states
```

Then reify the distinguishing frame as an object in the language:

```text
O := representation of the distinguisher / comparison frame
```

Once `O` is an ordinary object, syntax can form `O(O)`. The operation that was
originally a relation between an object and a frame has become an expression
whose argument may be the frame's own representation:

```text
relation / meta-operation
        |
        v  reification
ordinary object O
        |
        v
self-application becomes syntactically possible
```

This explains why self-reference can arise without postulating a mystical
observer. The engineering question is whether semantic grounding survived the
transition from meta-level frame to object-level term.

## The liar under DistinctionProfile

Let:

```text
L := "This statement is false"
L ≡ ¬Truth(L)
Assess(frame, proposition)
```

An ordinary typed profile may admit a truth predicate and analyse the fixed
point according to its own rules. Under `DistinctionProfile`, however, truth
assessment requires a grounded distinction between the proposition being
assessed and the assessment frame. The liar attempts to make the truth-status
of `L` a condition for determining the truth-status of `L` itself:

```text
unfounded self-grounding
    -> semantic admissibility failure
    -> C
```

The result is therefore profile-relative. It is not `SelfReference => C`; it is
`UngroundedSelfApplication(semantic_operator) => C` when the selected
`DistinctionProfile` cannot provide the required relational grounding.

## Boundary revealed by the failure

The paradox is valuable in this profile because the failure exposes a boundary
of the chosen conceptual system. The conclusion is not “there are no liars” or
“all self-reference is nonsense”. It is:

```text
this formalization + this grounding rule + this context -> C
```

Another semantic profile may type the truth predicate differently, provide a
fixed-point construction, or use a different relation between proposition and
assessment frame. Onto4 keeps those alternatives context-bound instead of
silently promoting one philosophical hypothesis to a universal law.
