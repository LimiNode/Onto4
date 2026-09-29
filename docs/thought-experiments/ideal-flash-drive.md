# The ideal flash drive: when information becomes physical state

This thought experiment is not the ordinary problem of a file storing its own
description. Its premise is stronger: **information is fully identical with
the carrier's physical state**.

The ideal flash drive has no separate layer of “carrier material plus stored
meaning”, filesystem, metadata or spare space for history. All of its physical
state is occupied by what has been written.

## What “ideal” means

An ordinary flash drive is roughly:

```text
drive material
      ↓ encodes
information about a brick
```

We can therefore distinguish the carrier, the code and the meaning. The
experiment removes that gap. To write an object is to bring the carrier into
exactly the physical state corresponding to the object.

```text
Write(brick)
Flash -> Brick
```

The drive does not contain a file describing a brick. In the physical sense
stipulated by the experiment, it becomes a brick:

```text
Flash == Brick
```

## A recorded brick and an ordinary brick

Compare two physically identical bricks. One arose normally; the other was
produced by `Write(brick)` on the ideal drive.

If there is no physical difference between them, the brick itself contains no
statement saying:

```text
“this brick used to be a flash drive”
```

For that distinction to be available, a carrier is needed:

```text
M := “this brick was produced by a write operation”
```

But `M` must itself be physically realized. The state is then:

```text
Brick + M
```

and the ideal condition is broken: additional matter or structure has appeared
beyond the state of the brick itself.

If the distinction is not physically represented anywhere, then within the
experiment a “recorded brick” and an “ordinary brick” are indistinguishable.
This does not assert that their histories must be the same; it says that the
history is not available as information without an additional carrier.

## Writing the same state again

Suppose the drive has already become a brick:

```text
S0 = Brick
```

Now perform again:

```text
Write(Brick)
```

and obtain:

```text
S1 = Brick
```

If the states before and after are absolutely identical:

```text
S0 = S1
```

the current state cannot reveal that a write occurred. It cannot distinguish:

```text
brick written 0 times
brick written 1 time
brick written 1000 times
```

To distinguish them we would need a counter:

```text
count = 1000
```

But a counter is additional physical state. We have again obtained:

```text
Brick + history / count / "was written"
```

Distinction shows where an extra state has been smuggled into the model.

## Carrier and meaning

We ordinarily write:

```text
physical_state = X
value = Brick
```

as if meaning were an independent entity attached to a physical state. The
ideal drive removes that escape: after the write, only the brick's physical
state remains.

If we still call it the “meaning of a brick”, we must specify a relation and a
context:

```text
Meaning(Brick, "recorded brick" | K)
```

where `K` may be an observer's memory, process history, language or another
structure in reality. The brick itself contains no label saying whose meaning
it carries.

Meaning is therefore not an immaterial layer on top of matter. Within this
experiment, what remains is:

```text
states of what exists
relations between those states
```

“Meaning” is a useful name for a particular structure of such relations.

## Consequence: complete self-representation

The experiment has a more familiar consequence as well. If the ideal drive must
contain a complete description of its own state `F`, writing the description
makes it part of that state:

```text
F -> F'
Encode(F) != Encode(F')
```

This creates a regress of levels. It is not the primary subject here: its role
becomes clear only after the more fundamental observation that meaning and
writing history require an additional physical distinction.

## Relation to Onto4

The experiment shows that:

1. information can be identified completely with physical state;
2. a recorded object and an ordinary object can be physically indistinguishable;
3. history, operation count and the fact of writing require additional state;
4. a carrier's state has no meaning without a context and representation
   relation;
5. distinction exposes where a hidden carrier is being added to the model.

A question about a “meaning” that exists in neither the system's state nor its
relations may therefore be neither false nor merely unresolved. First we must
check whether an admissible physical carrier for that meaning exists.

For the connection to the one-bit world and the liar paradox, see [“One-bit
world”](one-bit-world.md) and [“Distinction and the liar paradox”](../distinction-liar-paradox.md).

## Related ideas and research

These works do not prove the impossibility of exactly the ideal flash drive
described here. They help separate several related but non-identical problems:

- [Thomas Breuer, *The Impossibility of Accurate State Self-Measurements*](https://doi.org/10.1086/289852)
  studies which states cannot be distinguished exactly by an observer that is
  part of the system.
- [Charles S. Peirce: semiotics](https://plato.stanford.edu/entries/peirce/)
  presents meaning through the triad of object, sign and interpretant; this is
  close to the claim that physical state is not automatically its meaning.
- [W. K. Wootters and W. H. Zurek, *A Single Quantum Cannot Be Cloned*](https://doi.org/10.1038/299802a0)
  establishes a specific quantum limit on perfectly copying an unknown state.
  It is an analogy, not a general prohibition on copying or writing.
- [Alfred Tarski, *The Semantic Conception of Truth*](https://doi.org/10.2307/2102968)
  shows why formal object-language and metalanguage levels matter for a truth
  predicate. Here it is only a more distant formal parallel.

Onto4's own claim remains independent: meaning and writing history require an
explicitly selected physical state, relation and context.
