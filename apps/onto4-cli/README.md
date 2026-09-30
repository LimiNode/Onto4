# Onto4 CLI

Experimental Python CLI for evaluating Onto4 formalizations and comparing them
under different contexts.

The first implementation slice is deliberately deterministic. It contains no
LLM or KEV integration. Natural-language interpretation and typed decision
providers will be added behind explicit interfaces after the kernel is covered
by acceptance tests.

Only the `strict_onto4` semantic profile and `direct_evidence` inference
profile are implemented at this stage. Other profile values are rejected
instead of being silently treated as strict evaluation.

## Quick start

From this directory:

```text
python -m pip install -e .
onto4 eval examples/formalizations/has_mass_integer_7.yaml \
  --context profiles/contexts/physical_objects.yaml
onto4 compare examples/formalizations/identity_substance.yaml \
  --context profiles/contexts/continuity.yaml \
  --context profiles/contexts/process.yaml
```

The semantic contract is:

```text
Formalization + AssessmentContext -> AssessmentResult
```

An unresolved or missing formalization has no Onto4 verdict. It is not `U`:
`U` is reserved for an admitted, meaningful formalization whose `T/F` status
has not been established. Supporting `Evidence4` is not itself an established
truth verdict; explicit atomic truth entries are kept in a separate store.

For example, a context may keep the two axes explicit:

```yaml
truth:
  has_mass(car_A): T

evidence:
  has_mass(car_A): TrueOnly
```

If only the `evidence` entry is present, the result remains `U` with
`Evidence4 = TrueOnly`.

## Tests

```text
python -m pip install -e ".[test]"
python -m pytest -q
```

The suite includes the complete canonical strict tables for negation,
conjunction, disjunction, implication and equivalence.
