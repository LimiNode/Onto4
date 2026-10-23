# Onto4 architecture A/B experiment protocol

This document is the frozen protocol for the model-backed clarification
experiments. It is a research specification, not a semantic rule of Onto4.
The protocol separates model behaviour, host admission and deterministic
assessment so a provider failure is never reported as `U` or `C`.

## Variants

The first paired comparison keeps the initial `InterpretationSpace`, question,
user answer, context scope, model, runtime and request budget identical.

- **Full Snapshot**: the model proposes a complete successor
  `InterpretationSpace`; the host validates provenance and applies it.
- **Typed Delta**: the model proposes one operation from the bounded
  `RefinementOperation` set; the host applies it to the immutable snapshot.

The later factorial comparison has two interpretation conditions and two
refinement conditions:

| Variant | Initial interpretation | Refinement |
|---|---|---|
| A1 | `context_late` | full snapshot |
| A2 | `context_aware` | full snapshot |
| B1 | `context_late` | typed delta |
| B2 | `context_aware` | typed delta |

`context_late` is the existing baseline: interpretation sees the utterance and
formalization receives the permitted context. `context_aware` exposes only a
bounded projection of the selected context during interpretation. It never
exposes the hidden oracle, intended reading or future user answer.

## Frozen inputs and splits

The v2 philosophical corpus is immutable for a run. A run records its corpus
digest, context-profile digests, exact commit, model identifier, prompt
version/hash, temperature, thinking mode, maximum output tokens, request and
case deadlines, retry budget, evaluation variant and trial ID.

Development cases may be used to diagnose an adapter or prompt. A held-out
case is not used to choose a model output or revise a prompt. Any protocol
change increments the protocol version and starts a new run family.

## Outcomes and stopping rules

Every case records independent stages: interpretation, formalization, schema
validation, admission, assessment, clarification, refinement, reassessment and
final disposition. Each stage can fail operationally or semantically; provider,
JSON, schema and timeout errors remain operational outcomes.

The runner is sequential by default. A case may retry only within its bounded
request/case budget, and receipts are written atomically after each case. The
current transport seam is synchronous: if an injected executor is
non-cooperative, the runner does not claim a hard deadline or start another
request over it.

The smoke run stops and is reported before corpus expansion if the endpoint
cannot complete the basic arithmetic, category, evidence, historical,
contextual-ambiguity and two-turn dialogue controls. No offline fixture result
is labelled model-backed.

## Metrics

Semantic metrics are computed only where the deterministic oracle is defined:

- verdict and semantic-applicability accuracy;
- ontology and reading selection;
- preservation of user commitments;
- unsupported or falsely resolved presuppositions;
- correct refusal when the question remains underdetermined.

Dialogue metrics include unnecessary and missed questions, target coverage,
repeated questions, successful continuation and preserved open assumptions.
Operational metrics include completed cases, schema/provenance/timeout rates,
model calls, generated tokens when supplied, latency and turns to termination.

Report unconditional end-to-end success separately from conditional refinement
success on snapshots admitted by both methods. For paired cases report
win/loss/tie and the number of observations; do not declare a small difference
significant without enough independent trials.

## Review boundary

Cases without a determinate computational oracle receive a human-review label
such as `context_dependent` or `requires_human_review`. Formal correctness,
semantic fidelity and philosophical usefulness are reported separately. Bonsai
is a provider under test, not the sole judge of its own semantic correctness.

Raw user content, complete model responses and credentials are excluded from
public receipts by default. A local diagnostic trace may be enabled explicitly
with a documented retention and redaction policy.
