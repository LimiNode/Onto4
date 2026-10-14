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

# One model-backed interpretation/formalization/assessment pass
onto4 ask "What is the mass of integer 7?" \
  --endpoint http://127.0.0.1:8080/v1 \
  --model bonsai \
  --context profiles/contexts/physical_objects.yaml
```

`onto4 ask` performs one explicit pass and reports the deterministic landscape
and Onto4 assessments. It does not treat the model's text as a verdict. A
pending clarification and answer loop will be added as a subsequent CLI slice;
the current command is intentionally useful for inspecting model/schema
behavior before that loop is automated.

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

The first runtime-backed connection layer is `ProviderProfile` plus
`OpenAICompatibleClient`. It accepts an `http(s)` `base_url`, model name and
`none`/`bearer` authentication mode, and can test `/models` or call
`/chat/completions`. The profile is deliberately non-secret: a Bearer token is
passed to the client at runtime and is not part of the profile object. This
transport returns a validated JSON envelope only; it does not construct an
`InterpretationSpace`, formalization candidates or an Onto4 verdict. Those
adapters remain the next explicit boundary. The default transport does not
follow HTTP redirects, so a runtime credential cannot be forwarded to an
unexpected origin.

The formalization adapter receives a deterministic projection of the complete
`InterpretationSpace`, including ambiguity, ontology, presupposition and
reading IDs plus `presupposition_ids`. It must bind candidates to those supplied
readings rather than inventing or renaming provenance. An explicitly requested
`conceptual_depth` is likewise preserved by the interpretation adapter; a model
response that changes it is rejected.

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
    -> ClarificationQuestion
```

The request contains interpretation and landscape metadata only. The
deterministic layer derives the admissible workflow branch first; the provider
can refine that branch (for example, choose a clarification kind) or abstain,
but cannot replace it with another disposition or become an Onto4 verdict.
When several diagnostics justify different questions, the provider selects
only among those justified kinds. `FixtureClarificationPolicy` still owns the
question text, targets and user-facing choices. If it cannot realize the
selected kind from the same provenance, the bridge fails closed; an abstention
does not silently fall back to another question.
`T/F/U/C` remain exclusively produced by the core evaluator.

A selected question is stored as an immutable `PendingClarification` before it
is shown to the user. The later `apply_clarification_answer()` call uses that
exact question and does not invoke the provider again. It checks the current
interpretation, question identity, selected refinement and allowed answers,
then records a `ClarificationTurn` leading to a new `InterpretationSpace`
snapshot. The answer, transition record and successor snapshot are not a new
assessment: the caller must start the next explicit formalization and
assessment pass. Inconsistent provenance is rejected instead of being repaired
implicitly.

`record_clarification_turn()` is the deterministic history boundary for this
pass. It appends only an answered result with both a `ClarificationTurn` and a
successor; pending or abstained results leave the existing `ClarificationState`
unchanged. The recorded turn is a transition record, not evidence and not an
Onto4 verdict.

`ClarificationSession` binds that history to the exact current interpretation
snapshot and to at most one pending question. Issuing a question preserves the
current snapshot and history; applying its answer consumes the pending question,
appends the validated turn and advances to the returned successor. A second
question cannot be issued while the first remains pending, and a context with
the same identifier but different interpretation data is rejected. Session
advancement still performs no formalization or assessment: those remain an
explicit subsequent pass.

`reassess_session()` is that explicit pass. It formalizes the session's exact
current snapshot again, assesses the newly returned candidates and builds a new
`AskResult`; it does not reuse the previous candidates or assessments. The
result is wrapped in `SessionAssessment`, which retains the same immutable
interpretation snapshot and rejects use after the session has advanced. Thus a
clarification answer records a transition, while a new Onto4 assessment appears
only when the caller explicitly starts reassessment. A pending question blocks
reassessment until it has been answered or the provider has abstained.

`ReasoningSession` binds these two boundaries into one immutable workflow state:
the current `ClarificationSession` and its latest `SessionAssessment`. Issuing
a question uses the existing assessment and does not create another one;
answering records a transition but clears the assessment because it belongs to
the previous snapshot. The next `reassess_reasoning_session()` explicitly
builds a fresh assessment. A transition and an assessment therefore remain
different events even in the end-to-end deterministic workflow.

## Interactive evaluation corpus

The reserved corpus at `eval/clarification/corpus.yaml` contains everyday
utterances, hidden intended readings and control cases. The hidden oracle is for
the test driver only: the model sees the utterance, not the expected reading.
Evaluation is semantic rather than phrase-exact and is intentionally kept out
of the ordinary unit-test run until the interactive `onto4 ask` driver exists.
