# Onto4 CLI

Experimental Python CLI for evaluating Onto4 formalizations and comparing them
under different contexts.

The first implementation slice is deliberately deterministic. It contains no
LLM or KEV integration. Natural-language interpretation and typed decision
providers will be added behind explicit interfaces after the kernel is covered
by acceptance tests.

## Quick start

From this directory:

```text
python -m pip install -e .
onto4 eval examples/formalizations/mass_integer_7.yaml \
  --context profiles/contexts/physical_objects.yaml
onto4 compare examples/formalizations/identity.yaml \
  --context profiles/contexts/continuity.yaml \
  --context profiles/contexts/process.yaml
```

The semantic contract is:

```text
Formalization + AssessmentContext -> AssessmentResult
```

An unresolved or missing formalization has no Onto4 verdict. It is not `U`:
`U` is reserved for an admitted, meaningful formalization whose `T/F` status
has not been established.
