# The ideal flash drive: meaning and complete self-representation

This thought experiment concerns the boundary between a carrier's state, its
meaning and its description of itself. It is not about ordinary file copying,
but about a stronger requirement: a carrier must contain a complete description
of its own state, including the presence of that description.

## A complete description changes what it describes

Let the complete state of an ideal flash drive be `F`. Suppose the drive must
store its own complete description:

```text
F contains Encode(F)
```

The record `Encode(F)` becomes part of the carrier's state. After the write,
the state is different:

```text
F -> F'
```

The description computed for `F` is therefore not a complete description of
`F'`:

```text
Encode(F) != Encode(F')
```

Including the new record requires `Encode(F')`. Placing it changes the state
again:

```text
F' -> F'' -> F''' -> ...
```

This is not merely a shortage of storage. It is a self-referential dependency:
the description becomes part of the object it is supposed to describe
completely.

## What is actually impossible here

The experiment does not say that a device cannot store its serial number, a
memory image, a checksum or a partial description. What fails is the simple
closure:

```text
object = complete representation of object
```

when “complete” includes the placement of the description itself and the whole
structure is required to remain unchanged.

Practical systems handle this boundary with levels, external storage, fixed
formats, snapshots or a restricted description domain. They do not erase
self-reference; they explicitly choose the context in which the description
counts as sufficient.

## Carrier state and meaning

Suppose a physical cell is in state `1`. The state alone does not say that it
means:

```text
“Vasya is alive”
```

The relation between the bit and the proposition must be represented in a wider
system:

```text
Meaning(1, “Vasya is alive” | K)
```

Here `K` includes a language, encoding scheme, memory, convention or
interpretive process. Meaning is therefore not a second entity attached to a
physical state. It is a relation inside some system.

The same applies to a record about another object. If `b1` stores the past state
of `b0`, seeing `b1 = 0` is not enough; the system needs the relation:

```text
Represents(b1, previous_state(b0) | K)
```

Without `K` and the relation itself, there is no way to determine whose meaning
the `0` is supposed to carry.

## Self-representation and additional levels

Trying to place the representation relation inside the same object creates
another level:

```text
F
Encode(F)
Encode(F, Encode(F))
...
```

This does not mean that every practical regress is infinite in every
implementation. A system may stop at an accepted basis: an external format,
key or encoding scheme can be taken as given. In that case complete
self-representation has been replaced by a contextual description with an
explicit basis.

## Relation to Onto4

The ideal flash drive highlights several connected claims:

1. a carrier's state is not identical to its history or description;
2. a description included in an object changes that object;
3. meaning exists as a relation in a wider system;
4. self-representation requires a boundary, level or external basis;
5. an absolute point of view cannot be silently added when it is absent from
   the selected ontology.

Thus a question about complete meaning or complete description may be neither
false nor merely unresolved. First we must check whether the operation itself
is admissible in the selected context. For the connection to self-reference and
the verdict `C`, see [“Distinction and the liar paradox”](../distinction-liar-paradox.md).

## Related ideas and research

These works do not prove the impossibility of exactly the ideal flash drive
described here. They help separate several related but non-identical problems:

- [Thomas Breuer, *The Impossibility of Accurate State Self-Measurements*](https://doi.org/10.1086/289852)
  studies which states cannot be distinguished exactly by an observer that is
  part of the system.
- [Charles S. Peirce: semiotics](https://plato.stanford.edu/entries/peirce/)
  presents meaning through the triad of object, sign and interpretant; this is
  close to the claim that a carrier's state is not automatically its meaning.
- [W. K. Wootters and W. H. Zurek, *A Single Quantum Cannot Be Cloned*](https://doi.org/10.1038/299802a0)
  establishes a specific quantum limit on perfectly copying an unknown state.
  It is an analogy, not a general prohibition on copying or self-representation.
- [Alfred Tarski, *The Semantic Conception of Truth*](https://doi.org/10.2307/2102968)
  shows why formal object-language and metalanguage levels matter for a truth
  predicate. Here it is only a more distant formal parallel.

Onto4's own claim remains broader and independent: meaning and complete
description require an explicitly selected context, level and carrier.
