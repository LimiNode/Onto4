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

## Provider boundary

Interpretation and formalization are separate provider steps:

```text
InterpretationRequest (source text + optional conceptual depth)
    -> InterpretationSpace
    -> FormalizationRequest
    -> FormalizationCandidate[]
```

The provider contracts return only meta-level interpretations and explicit
candidate structures. Assessment remains a separate call to the deterministic
Onto4 core. `FixtureInterpretationProvider` routes by
`(source_text, conceptual_depth)`; `FixtureFormalizationProvider` is then
keyed by the immutable `InterpretationSpace.id`. Equal source text therefore
does not collapse different interpretation snapshots. A candidate's
`reading_id`, when present, must refer to a reading in the supplied space and
is checked fail-closed by the fixture. Candidate assumptions must be traceable
to its presuppositions or explicitly introduced during formalization; that
assumptions provenance is a normative contract and is not machine-validated in
this slice. These fixtures do not implement natural-language understanding,
LLM behavior or KEV behavior.

## Clarification-aware orchestration

The next deterministic layer treats `ask` as an iterative workflow rather
than a one-shot verdict request:

```text
InterpretationRequest
    -> InterpretationSpace
    -> FormalizationCandidate[]
    -> AssessmentLandscape
    -> Complete | AskClarification | NeedEvidence | CannotProceed
```

`FixtureClarificationPolicy` emits typed, provenance-aware questions and keeps
clarification turns as immutable successor snapshots. A clarification is not
an Onto4 verdict: semantic ambiguity and unresolved reference lead to a
question, missing evidence leads to `NeedEvidence`, an admitted category
mismatch remains `C`, and an invalid request follows `CannotProceed`.
Unknown formalization causes remain `Formalization` clarification until a
diagnostic establishes a more specific cause; context dependence is likewise
reported neutrally as `Context` rather than being attributed to perspective.
Clarification targets use stable IDs, and successor turns must form a
continuous interpretation chain.

The provider roadmap keeps responsibilities separate. Interpretation and
formalization providers may later be model-backed, while typed decision
providers remain bounded scorers or classifiers. Deterministic policy decides
the next workflow action; no global confidence threshold is assumed, and any
future threshold belongs to a versioned decision profile. Batched typed
questions remain possible over one shared state. These engineering constraints
do not define canonical Onto4 semantics.

## Typed decision substrate

`TypedDecisionProvider` is a bounded, profile-scoped signal source. A
`DecisionProfile` owns the stable schema identity (`id` + `version`), choices,
calibration metadata and abstention policy. Confidence is not a universal
probability and no global acceptance threshold is applied. The deterministic
consumer may use a valid choice, or handle explicit abstention, but it never
produces `T/F/U/C`.

Decision results carry mandatory profile id/version provenance. A valid
decision is either a profile choice or an explicit abstention (`choice=None`);
the two states are not inferred from one another. `TypedDecisionBatchProvider`
is optional: providers that support it answer several typed questions over one
shared state and reject mixed-state batches. `FixtureDecisionProvider` is
question-keyed and intentionally does not model a state-sensitive scorer;
`FixtureBatchDecisionProvider` covers the shared-state contract without
selecting a real model or implementing KEV/Jev behavior.

The clarification bridge uses this substrate in a bounded direction:

```text
ClarificationContext
    -> TypedDecisionRequest
    -> TypedDecisionProvider
    -> DeterministicDecisionPolicy
    -> PipelineDisposition
```

The request contains interpretation and landscape metadata only. The
deterministic layer derives the admissible workflow branch first; the provider
can refine that branch (for example, choose a clarification kind) or abstain,
but cannot replace it with another disposition or become an Onto4 verdict.
`T/F/U/C` remain exclusively produced by the core evaluator.
