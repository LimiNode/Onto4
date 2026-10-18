# Onto4 CLI

Experimental Python CLI for evaluating Onto4 formalizations and comparing them
under different contexts.

The semantic kernel is deliberately deterministic. Model-backed interpretation
and formalization are available behind explicit provider interfaces, while KEV
integration and model authority over Onto4 verdicts remain out of scope. The
CLI keeps provider output, host-controlled orchestration and deterministic
assessment as separate boundaries.

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
and Onto4 assessments. It does not treat the model's text as a verdict. The
single-pass mode remains useful for inspecting model/schema behavior; the
bounded interactive mode below adds explicit clarification and reassessment.

The command also supports a bounded host-controlled interactive pass:

```text
onto4 ask "Настоящая личность человека определяется его генами." \
  --endpoint http://127.0.0.1:8080/v1 \
  --model bonsai \
  --context profiles/contexts/identity_and_genome.yaml \
  --interactive --max-turns 4
```

Interactive mode uses the per-reading/context formalization boundary. The host
owns `ReasoningSession`, pending-question identity, successor provenance and
explicit reassessment. The model may propose only semantic content for the
next interpretation snapshot. A free-form answer is allowed, including
`none_of_the_above`; that answer preserves the current semantic snapshot
instead of forcing a false choice. The host also keeps a clarification progress
ledger, rejects repeated semantic question targets, classifies each transition
as resolved, structural-resolution, unresolved, new, no-effect, unverified or abstained, and rejects a changed snapshot that
does not affect the question's target distinction. If no new admissible
question remains, the bounded loop stops explicitly instead of repeating the
same question. A model response that changes source text, conceptual depth or
produces no semantic successor is rejected.

Provider generation is bounded by `--max-output-tokens` (default `1024`) and
structured stages disable provider-side hidden thinking by default. This keeps
the output budget for the required JSON envelope instead of spending it on an
internal reasoning trace. Sampling is deterministic by default
(`--temperature 0`); `--enable-thinking` is an explicit opt-in for endpoints
that support the `chat_template_kwargs` extension. These are
transport/runtime policies; schema and provenance validation remain fail-closed.

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

The runtime-backed CLI uses a bounded host-selected fan-out for this step:

```text
InterpretationSpace
    -> one FormalizationRequest per (reading, context)
    -> host-bound candidate identity
    -> deterministic assessment
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

The typed-delta path is an experimental model-backed execution mode. The
offline corpus executor records protocol coverage only and does not apply typed
deltas; `eval-corpus --mode offline --refinement-mode typed_delta` is rejected
instead of being recorded as if typed refinement had run. Every typed batch is
also bounded by a host-side limit of 16 operations, enforced before any
snapshot or commitment can change.

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

## Explicit refinement deltas (opt-in research boundary)

`onto4.pipeline.refinement` provides a bounded typed-delta experiment for
interactive research. A model may propose operation content such as
`select_reading`, `refine_ambiguity`, `add_presupposition` or `abstain`, but the
host supplies the exact assessment-bound snapshot, admissible target IDs and
the successor ID. The host then validates references and applies the delta to
an immutable `InterpretationSpace`.

Reading selection names the ambiguities it resolves; unrelated ambiguities are
preserved. Batch application returns the complete ordered commitment list and
publishes no partial result if any operation is rejected. A changed snapshot
ID alone is explicitly a no-effect transition.

This layer records structural admission and provenance; it does not establish
that a model understood the user's meaning, and it never produces `T`, `F`,
`U` or `C`. `retain_ambiguity` is explicitly represented as a no-effect
operation, while `abstain` preserves the current snapshot. The experiment is
not part of the default `onto4 ask` path until comparative fixture results
justify adopting it.

## Controlled architecture A/B benchmark

The `benchmark` command provides a paired experiment for the two independent
design choices in the model-backed clarification path. It runs the same public
corpus through four cells:

```text
             full_snapshot       typed_delta
context_late      A1                  B1
context_aware     A2                  B2
```

`A1` versus `B1` and `A2` versus `B2` are the refinement comparisons.
`A1` versus `A2` and `B1` versus `B2` are the context-timing comparisons. The
pairing is by stable `case_id`; a cell is not compared with a different
utterance or a different corpus version. This runner is explicitly an
**E2E paired-by-case** experiment: it does not claim that the model produced
identical initial `InterpretationSpace` snapshots in the four cells.

The starter corpus is
`eval/clarification/ab-philosophical-smoke.yaml`. It is deliberately small
and executable: continuity and substance provide same-utterance controls, and
the genome and intrinsic-time cases exercise bounded clarification dialogues.
The hidden expected readings remain in the corpus for the evaluation driver;
they are not included in model-facing input. This smoke corpus is contextual:
the `context_late` cells receive the case context identifier, while
`context_aware` additionally receives the bounded ontology projection. This
keeps the context-timing comparison executable rather than silently running
the same interpretation input in all four cells.

Run it against an OpenAI-compatible endpoint with:

```text
onto4 benchmark \
  --corpus eval/clarification/ab-philosophical-smoke.yaml \
  --endpoint http://127.0.0.1:8080/v1 \
  --model bonsai \
  --context profiles/contexts/continuity.yaml \
  --context profiles/contexts/substance.yaml \
  --context profiles/contexts/identity_and_genome.yaml \
  --context profiles/contexts/relational_time.yaml \
  --artifacts-dir artifacts/ab-smoke \
  --report artifacts/ab-smoke/report.json
```

Each cell writes privacy-preserving receipts. The paired report keeps three
axes separate:

```text
execution: successful | failed | incomplete | unsupported
workflow:  correct | incorrect | unverified | not_comparable
semantic:  correct | incorrect | unverified | not_comparable
```

Schema/provenance failures and exhausted scripts therefore do not become
semantic errors. A semantic mismatch is counted only when a successful cell
has a sufficient semantic oracle. Unknown clarification-turn counts remain
`null`, rather than being reported as zero. The report also contains per-cell
execution/workflow/semantic counts, success denominators, all four pairings,
safe workflow diagnostics and the exact run configurations. An omitted
`--output-cost-per-million` is recorded as `not_priced` with a `null` cost;
prompt-token costs are never inferred.

For a true refinement comparison, use the isolated protocol API
`run_model_backed_isolated_refinement_pair()`. This is the
`provider_isolated_refinement` protocol: one immutable initial snapshot, one
question and one scripted answer are passed independently to the two
providers. It does not prove that the question was issued by a live session.
For that stronger claim use
`run_session_bound_isolated_refinement_pair()`, which requires a current host
assessment and its immutable `PendingClarification`; arbitrary reconstructed
questions are rejected. Their accepted transitions and
semantic-obligation digests are reported separately from E2E metrics.

Reports should include a source SHA, model artifact digest, prompt
version/hash, context digests, sampling settings, backend description, oracle
version and run identifier. A single condition order is not a latency claim;
repeat runs with a warm-up and permuted condition order before comparing
timings.

The benchmark does not turn a model response into an Onto4 verdict. `T`, `F`,
`U` and `C` still come only from the deterministic core, and no semantic
fidelity claim is made without an oracle comparison. The command also writes a
safe per-case diagnostics report; it contains stages, counts, provenance
codes and failure classes, never prompts, raw model payloads or credentials.

### Bounded multi-turn research

`eval/clarification/bounded-dialogue-v1.yaml` is a dialogue-only research
corpus for the genome-identity and intrinsic-time cases. Each scenario allows
two bounded clarification questions. The research helper
`run_bounded_dialogue_research()` reports the stages independently:

```text
question candidate generated
    -> question selected
    -> intent admitted
    -> question issued
    -> answer consumed
    -> refinement accepted
    -> reassessment performed
```

An incomplete or unknown stage is not promoted to a completed dialogue or a
semantic success. A corpus must be preflighted against host-owned intents
(`discover_host_question_intents()` and
`validate_dialogue_intent_manifest()`); the preflight is a frozen binding and
does not rewrite the oracle after a scored run. For a model-backed refinement comparison,
`run_model_backed_isolated_refinement_pair()` sends the same immutable initial
snapshot, question and answer to Full Snapshot and Typed Delta providers; the
host still owns IDs, transition provenance and all Onto4 assessment semantics.

## Interactive evaluation corpus

The reserved corpus at `eval/clarification/corpus.yaml` contains everyday
utterances, hidden intended readings and control cases. The hidden oracle is for
the test driver only: the model sees the utterance, not the expected reading.
Evaluation is semantic rather than phrase-exact and is intentionally kept out
of the ordinary unit-test run until the interactive `onto4 ask` driver exists.
