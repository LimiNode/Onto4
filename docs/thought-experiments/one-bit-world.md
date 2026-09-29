# The one-bit world: change without an outside observer

This thought experiment concerns distinction, memory and the impossibility of
an absolute point of view “outside” a system. It does not claim that physical
reality literally consists of one bit.

## A world with one bit

Imagine an isolated world containing only one bit:

```text
b ∈ {0, 1}
```

Let it have value `0` at `t1` and value `1` at `t2`:

```text
b(t1) = 0
b(t2) = 1
```

An observer imagined outside the world can easily write:

```text
b(t1) != b(t2)
b changed
```

But that statement already uses additional structure: two times, access to
both states and a relation between them. At `t2` the bit is simply in state
`1`; that state does not by itself say that it was `0` before.

The current bit does not store its own history. For the change to become
information, a carrier is needed:

```text
D(b(t1), b(t2) | K)
```

Here `K` is a process, memory, measurement system or other context in which the
two states are compared.

## The outside position is part of the description

The imagined outside observer is useful precisely because it exposes the
missing structure. It has access to both `b(t1)` and `b(t2)` and stores the
relation between them.

But it is not a real view from outside all reality. If an observer physically
exists, it is itself part of a wider system. Its memory, measurement and record
form context `K`, not an absolute external position.

Thus the statement:

```text
“the bit changed”
```

always means that a change was established relative to some process, state or
carrier of comparison. It is not a context-free assertion about a value that
exists independently of every relation.

## Trying to embed the observer

Now add a second bit:

```text
b0 = observed bit
b1 = supposed memory of b0's past
```

Suppose `b0` is now `1` and `b1 = 0` is intended to mean “`b0` used to be
`0`.” Physically, however, `b1 = 0` says only that the second bit is in state
`0`.

The relation:

```text
b1 represents the previous state of b0
```

is not contained in the bare state of `b1`. It requires another structure:

```text
R := Represents(b1, previous_state(b0))
```

`b1` is privileged not because it contains a special “meaning”, but because a
wider system uses it to store the state of another element. The system must
also specify where and how the relation `R` is represented.

This exposes the difference between:

```text
state of a bit
meaning assigned to that state
```

The second is not an automatic property of the first.

## Contextual distinction

The one-bit world illustrates the general pattern:

```text
D(A, B | K)
```

Distinction arises in a concrete act, process or system state. It may be a
physical measurement event, a memory record, a transition or a model. The mere
presence of two labels `A` and `B` does not create information about how they
are distinguished.

When distinction is used in reasoning, it needs a carrier:

```text
C := Distinguishes(A, B | K)
```

The outside observer in the experiment is a useful abstraction of such a
carrier. It does not add a metaphysical entity beyond the world; it temporarily
moves the comparison context outside the fragment being described.

## What the experiment shows

The one-bit world does not prove that change is impossible or that systems
cannot store history. It shows a more precise limitation:

1. a current state is not identical to its history;
2. establishing change requires additional structure;
3. an embedded observer becomes part of the observed system;
4. a carrier's state and its assigned meaning require a representation
   relation;
5. an absolute outside view cannot be silently added to a model after the
   fact.

This boundary matters for Onto4: a question may be neither `F` nor `U` when it
presupposes a distinction context that the selected ontology does not provide.

For the next step, see [“The ideal flash drive”](ideal-flash-drive.md) and
[“Distinction and the liar paradox”](../distinction-liar-paradox.md).

## Related ideas and research

The following works do not prove Onto4's claims and do not define its normative
semantics. They provide related lines of thought:

- [Carlo Rovelli, *Relational Quantum Mechanics*](https://doi.org/10.1007/BF02302261)
  treats physical values as arising relative to another physical system in an
  interaction, rather than as properties fixed outside every relation.
- [Thomas Breuer, *The Impossibility of Accurate State Self-Measurements*](https://doi.org/10.1086/289852)
  formulates limits on accurate self-measurement by an observer that is part of
  the observed system.
- [Wojciech H. Zurek, *Quantum Darwinism*](https://doi.org/10.1038/nphys1202)
  connects accessible objectivity with multiple physical records in an
  environment.
- [G. Spencer-Brown, *Laws of Form*](https://doi.org/10.2307/2272151)
  treats distinction as a primary act of drawing a boundary.

Onto4 uses these works only as philosophical and physical analogies. Its
claim here is narrower: a change becomes information only in a context where it
is physically or symbolically represented.
