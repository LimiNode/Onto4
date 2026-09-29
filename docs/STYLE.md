# Onto4 documentation style

This guide applies to conceptual documentation, philosophy notes, thought
experiments, examples, architecture rationale and explanatory README sections.
Formal specifications may intentionally use a denser style.

## Explain before formalizing

A reader should understand the problem before encountering notation.

Poor order:

```text
D(A, B | K)
R := Represents(D(A, B | K))
```

Better order:

> A physical interaction may distinguish two states. If another part of the
> system must retain that distinction, a separate representation is needed.

Then introduce:

```text
D(A, B | K)
R := Represents(D(A, B | K))
```

## Preserve the load-bearing idea

Before rewriting, record privately:

- Core claim — what is the author actually saying?
- Essential distinction — which concepts must not be merged?
- Rejected assumption — what familiar interpretation is being challenged?
- Load-bearing example — which example carries the reasoning?
- Non-goals — what is the text explicitly not claiming?

If a rewrite changes one of these, it is not merely a stylistic rewrite.

Examples from Onto4:

```text
ideal flash drive
!= generic complete-self-description paradox

distinction event
!= representation of distinction

observer
!= necessarily a human or metaphysical subject

context dependence
!= epistemic uncertainty
```

If an idea resembles a familiar concept, state the difference explicitly rather
than silently normalizing it.

## Keep layers separate

Many Onto4 arguments depend on level distinctions:

```text
D(A, B | K)                  -- act of distinction
R := Represents(D(A, B | K)) -- representation of that act
```

The same discipline applies to:

- state and meaning of the state;
- transition and record of the transition;
- physical interaction and knowledge about it;
- observed sequence and intrinsic time;
- model and reality;
- syntax and semantic admissibility.

Do not call all of these “information about the event” if that erases the
distinction between event and representation.

## Context is part of the claim

Use context explicitly when the argument depends on it:

```text
D(A, B | K)
Changed(b | K)
V(P | ontology, semantics, epistemics, inference, perspective)
```

Make clear which structure belongs to the modeled system and which belongs to an
observer, language or formal model. Do not assume an absolute history, meaning,
identity-through-time or viewpoint on all reality without declaring it.

## Write thought experiments as arguments

Expose the structure the reader is likely to import unconsciously.

For the one-bit world, examine:

```text
b
-> {0,1}
-> t0, t1
-> order
-> memory
-> identity across observations
-> “the bit changed”
```

For the ideal flash drive, ask:

- What makes a recorded brick different from an ordinary brick?
- Where is that difference represented?
- What changes when the same brick is written again?
- Where would the number of writes be stored?
- What does “value” mean once carrier and stored state coincide?

Examples are part of the argument, not disposable decoration.

## Prose and rhythm

Write like a strong engineer or researcher explaining an idea at a whiteboard.
Prefer concrete examples, causal verbs, short or medium paragraphs and one
conceptual step at a time.

Avoid chains of abstract nouns, corporate prose, decorative terminology,
repetitive summaries and excessive defensive caveats. Do not write an
explanation of an explanation before presenting the idea itself.

For Russian prose, remove unnecessary English and translated-English syntax.
Keep identifiers such as `Truth`, `DistinctionProfile`, `Evidence4` and
`UngroundedSelfApplication` unchanged.

Poor:

> В рамках текущего профиля наблюдатель представляет собой абстрагированный
> механизм семантического различения, осуществляющий репрезентацию отношений.

Better:

> Если Вася и Петя различены в памяти, датчике или записи, именно этот носитель
> представляет различие в выбранном контексте.

## References and related work

References provide context, not authority proof. State the exact overlap and
the limit of the analogy:

> This interpretation is not derived from the following work. It provides a
> related line of thought about values being relative to interactions.

Distinguish Onto4's claims from analogies, established mathematical results,
physical interpretations and philosophical similarities.

## Algorithms and technical explanations

For algorithm explanations, use this order when practical:

1. problem;
2. why the obvious solution is insufficient;
3. core idea;
4. one small example;
5. invariant;
6. pseudocode or implementation;
7. complexity;
8. edge cases and failure modes;
9. optimizations and variants.

Do not begin with pseudocode or asymptotic notation unless the page is a
reference specification. Explain why the algorithm works before its mechanics.

## Normative status

Say whether a passage is a canonical rule, a profile-relative interpretation,
an example, a research note or a historical record. Canonical documentation
should describe the current model, not repository archaeology.
