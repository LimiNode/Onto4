---
name: conceptual-writing
description: Write and review Onto4 philosophical and conceptual documentation while preserving semantic distinctions and load-bearing thought experiments.
---

# Conceptual Writing

Use this skill for philosophy notes, thought experiments, semantic
explanations, conceptual README sections, architecture rationale and
algorithm explanations where intuition matters. Do not use it for pure API
reference or mechanical specification tables.

## Before writing

Read:

1. the target document;
2. nearby canonical documents;
3. `AGENTS.md`;
4. `docs/STYLE.md`;
5. `docs/WRITING-CHECKLIST.md`.

Before drafting, identify privately:

```text
Core claim:
Essential distinction:
Rejected assumption:
Load-bearing example:
Likely misunderstanding:
Non-goals:
```

Do not draft until these are clear.

## Drafting procedure

1. Explain the concrete problem in plain language.
2. Walk through the load-bearing example.
3. Show the hidden assumption or failure.
4. Introduce only the notation needed for precision.
5. State consequences and limitations.
6. Add related work with explicit limits of analogy.
7. Remove meta-commentary and unnecessary terminology.

## Adversarial review

Before finishing, ask:

- Did I replace the author's idea with a familiar textbook concept?
- Did I introduce realism, physicalism, observer-independent time or another
  unstated assumption?
- Did I confuse an event with its representation?
- Did I confuse a state with its meaning?
- Did I confuse lack of evidence (`U`) with semantic inapplicability (`C`)?
- Did I make self-reference automatically `C`?
- Did I promote a profile into universal Onto4 semantics?
- Did I import repository history into a normative document?
- Can a new reader follow the argument without knowing previous revisions?
- Did English terminology leak unnecessarily into Russian prose?

For Onto4, preserve these examples exactly when they carry the argument:

```text
ideal flash drive != generic self-description paradox
distinction event != representation of distinction
observer != necessarily an external subject
context dependence != epistemic uncertainty
self-reference != category error
```
