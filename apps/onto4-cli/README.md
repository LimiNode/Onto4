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
verdict; explicit atomic verdict entries are kept in a separate store.


For example, a context may keep the two axes explicit:

```yaml
verdicts:
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

Admission uses an explicit decisive-C policy for mixed diagnostics: an invalid
request takes precedence over a category error, and a category error takes
precedence over an unresolved sibling. An unresolved-only formalization still
has no Onto4 verdict.

## Interpretation space

The next deterministic layer keeps one natural-language question separate from
the formalizations that may be derived from it:

```text
InterpretationSpace
    -> FormalizationCandidate[]
    -> AssessmentResult per candidate
    -> AssessmentLandscape
```

`AssessmentLandscape` is a meta-level result. It can be
`StableAcrossCandidates`, `ContextDependent`, `FormalizationConflict` or
`MixedDependence`, `FormalizationUnresolved` or `InvalidRequest`; it never
replaces the Onto4 verdict of an individual candidate. `ContextDependent` is
reserved for one formalization assessed in different contexts. If both the
formalization and context axes change, the result is `MixedDependence` instead
of an unsupported causal attribution. LLM and KEV providers are not needed for
this layer.

`formalization_id` is an explicit identity claim: candidates sharing it must
have equal formalization structure and assumptions. The aggregator rejects a
landscape with a conflicting claim as `InvalidRequest` rather than trusting an
inconsistent identifier.
