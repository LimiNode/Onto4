# The one-bit world: whose time and whose change?

This thought experiment concerns distinction, time, observation and the danger
of silently importing the observer's structure into the observed world. It does
not claim that physical reality literally consists of one bit.

## A world containing one bit

Imagine an ontology in which only one bit is given:

```text
b ∈ {0, 1}
```

The next step usually looks obvious:

```text
b(t0) = 0
b(t1) = 1
```

and therefore:

```text
b changed
```

But this is where the experiment begins. Where did `t0` and `t1` come from? The
world was stipulated to contain only the bit. No clock, memory, time scale,
order relation `t0 < t1` or even intrinsic time was specified.

## What is actually observed

To say “first I saw `0`, then `1`”, an observer needs at least two of its own
states:

```text
N0 := “observed 0”
N1 := “observed 1”
```

and an order between them:

```text
N0 -> N1
```

Memory, sequence and difference are present in the observer's structure:

```text
D(N0, N1 | K_observer)
```

The statement:

```text
“the one-bit world changed”
```

is an interpretation of that difference. It may be useful in an extended
system, but it does not follow automatically from the bit's state alone.

## Whose time is it?

An outside observer inevitably has its own order of states. That order makes it
possible to say “earlier” and “later”. But time in the observer does not prove
that the same time exists inside the one-bit ontology.

We observe a possible sequence of bit states **in our time**, then tend to
attribute that time to the bit itself. Such a transfer may be part of a chosen
model, but it is not a free-standing fact.

For an internal claim `Changed(b)` to be meaningful, the ontology must provide
at least:

1. two distinguishable states;
2. an order relation between them;
3. a carrier of that order;
4. a criterion that both states belong to the same object.

If all of these belong only to the observer, the question concerns the system
“bit plus observer”, not the bit by itself.

## An embedded observer

We may try to add a second bit:

```text
b0 = observed bit
b1 = supposed memory of b0's state
```

But the second bit is no longer a neutral observer. It stores another element's
state, and its own state requires an interpretation:

```text
R := Represents(b1, state(b0) | K)
```

The system must also specify when `b1` stores a past state, a current state and
how those cases are distinguished. The embedded observer becomes part of the
system and brings a new structure of relations, not an absolute point of view.

## The contextual form of the question

Instead of the context-free:

```text
Changed(b)
```

we should write:

```text
Changed(b | K)
```

where `K` contains memory, order, object identity and a way to compare states.
If `K` is supplied by a physical process or an observer model, the question may
be meaningful in that extended system.

If the question is declared to concern a world containing only `b`, while time,
identity and order are silently imported from the outside observer, the problem
is not missing data. We have assigned the system a structure absent from its
ontology:

```text
Changed(b) -> C
```

This is a category error, not merely an unknown answer `U`.

## What the experiment shows

The one-bit world exposes a more fundamental limitation than lack of memory:

1. observing a sequence is not proof of intrinsic time;
2. the observer's state and the observed world's state play different roles;
3. change, past and sequence require an explicitly specified context;
4. an embedded observer becomes part of the observed system;
5. meaning and distinction arise in relations, not automatically in one isolated
   state.

The thought experiment deliberately prevents us from treating the structure of
observation as an objective property of the world after the fact. It prepares
the transition to [“The ideal flash drive”](ideal-flash-drive.md) and
[“Distinction and the liar paradox”](../distinction-liar-paradox.md).

## Related ideas and research

The following works do not prove Onto4's claims and do not define its normative
semantics. They provide related lines of thought:

- [Carlo Rovelli, *Relational Quantum Mechanics*](https://doi.org/10.1007/BF02302261)
  treats physical values as arising relative to another physical system in an
  interaction.
- [Thomas Breuer, *The Impossibility of Accurate State Self-Measurements*](https://doi.org/10.1086/289852)
  formulates limits on accurate self-measurement by an observer that is part of
  the observed system.
- [Wojciech H. Zurek, *Quantum Darwinism*](https://doi.org/10.1038/nphys1202)
  connects accessible objectivity with multiple physical records in an
  environment.
- [G. Spencer-Brown, *Laws of Form*](https://doi.org/10.2307/2272151)
  treats distinction as a primary act of drawing a boundary.

Onto4 uses these works only as philosophical and physical analogies. Its claim
here is narrower: a question about change requires explicitly given time, order,
identity and a carrier of distinction.
