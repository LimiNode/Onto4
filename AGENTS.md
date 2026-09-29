# Onto4 contributor route

Onto4 contains a canonical four-valued semantic model, explanatory philosophy
and thought experiments. Read the target document and nearby canonical material
before changing a conceptual contract.

## Documentation and conceptual writing

When editing philosophy, thought experiments, semantic explanations or
conceptual README sections, preserve the author's actual argument. Do not
replace an unusual idea with the nearest familiar textbook concept.

Before rewriting a conceptual passage, identify:

1. the central claim;
2. the example carrying the argument;
3. the assumptions the argument rejects;
4. the distinctions that must survive;
5. the most likely misunderstanding by a new reader.

A stylistic rewrite must not change any of these.

Prefer this explanatory order:

1. concrete problem or intuition;
2. simple example;
3. what becomes impossible, ambiguous or hidden;
4. notation and formalization;
5. consequences;
6. limitations and related work.

Do not begin with caveats, repository history or formal notation unless the
document is explicitly a specification. Explain the idea before explaining how
the idea should be interpreted.

### Onto4 conceptual invariants

Do not silently collapse:

- an object or state and its representation;
- distinction event `D` and representation `R` of that distinction;
- physical interaction and knowledge about that interaction;
- state and meaning assigned to that state;
- an observed sequence and intrinsic time of the observed system;
- context-relative distinction and absolute distinction "in itself";
- `U` and `C`;
- Evidence4 and Onto4;
- self-reference and `C`;
- `DistinctionProfile` and universal Onto4 semantics;
- an operational short-circuit result and a canonical strict result.

Use these symbols consistently:

```text
C  canonical Onto4 semantic/category verdict
K  context
D  act or relation of distinction
R  representation or carrier of a distinction
```

Do not reuse them for unrelated roles in one document.

Do not silently introduce an absolute observer, observer-independent time,
hidden absolute history or observer-independent meaning without declaring the
additional ontology that provides it.

### Avoid normalization into a familiar concept

Preserve the more specific idea present in the source material. In particular:

- the ideal flash drive is not merely a generic self-description paradox;
- a distinction event is not the representation of that event;
- an observer is not necessarily a human or metaphysical subject;
- context dependence is not ordinary epistemic uncertainty;
- self-reference is not automatically a category error.

### Russian prose

Write natural Russian rather than translated English. Keep English for
identifiers, established proper names and symbols. Prefer:

- `семантическая допустимость` over `semantic admissibility`;
- `основание` over `grounding` in ordinary prose;
- `строгая семантика` over `strict-семантика`;
- `категориальная ошибка` over `category error`;
- `неподвижная точка` over `fixed point`.

See [`docs/STYLE.md`](docs/STYLE.md) and run
[`docs/WRITING-CHECKLIST.md`](docs/WRITING-CHECKLIST.md) before committing.
