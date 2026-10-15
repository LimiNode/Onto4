# Clarification evaluation corpus

This corpus is reserved for the interactive `onto4 ask` vertical slice. It is
not part of the ordinary unit-test suite and is not passed to the model as a
prompt.

Each case contains an `utterance` visible to Onto4 and one or more hidden
scenarios known only to a test driver. A hidden scenario describes the user's
intended reading, not a required wording for the clarification question.

The evaluation should score semantic behavior rather than phrase matching:

1. Did the system preserve a material ambiguity when one exists?
2. Did it avoid inventing an unrelated ambiguity?
3. Did the question distinguish the intended readings?
4. Did it avoid assuming the hidden answer before asking?
5. Did the answer remove incompatible readings and retain the selected one?
6. Did it preserve the meaning of the answer in the successor snapshot?
7. Did it reach formalization after enough clarification?
8. Did it avoid asking again about an established distinction?
9. Did it keep unresolved formalization separate from `U`?
10. Did a meaningful control case avoid unnecessary clarification?

The first six cases are intended for early local-model runs. The control cases
ensure that the model does not learn the bad rule “always ask a question”. The
same utterance may occur in multiple scenarios: the initial model input must be
identical, while the hidden intended reading differs.

The current file is an oracle specification, not a golden transcript. Exact
question text, ordering and model phrasing must not be treated as correctness
criteria.

## Epistemic and ontological evaluation layer

`epistemic-ontology-v1.yaml` is a second, deliberately separate corpus. It
does not replace `everyday-clarification-v1`; it adds cases where a model can
fail by applying common knowledge or a modern theory before the selected
ontology and evidence policy are fixed.

The cases cover four distinctions that must remain separate:

- `U`: a meaningful claim for which the corpus supplies no adequate evidence;
- `C`: a predicate or category that is inapplicable in the selected ontology;
- ontology-dependent historical theories, such as caloric or phlogiston;
- reference or presupposition failure, which is not automatically `C`.

Some cases are explicitly marked as dialogue scenarios. Their hidden oracle
expects an ontology clarification before an evidence question or assessment.
The oracle is a test-driver contract, not a command to emit a fixed question.
In particular, model pretraining must not be treated as an implicit
`EvidenceStore`: an unusual statement is not false merely because the model
has never encountered evidence for it.

`genetic-essentialism-dialogue` is the first multi-turn protocol fixture. Its
sequence is intentionally stronger than a single clarification:

```text
claim
  -> ontology question
  -> free-form answer
  -> successor InterpretationSpace
  -> explicit reassessment
  -> identity-criterion question
  -> another answer or `none_of_the_above`
```

The CLI now has a bounded interactive runner that can execute this sequence
when supplied with model-backed interpretation, refinement and formalization
providers. The host-controlled loop owns snapshot identity, transition
provenance, progress admission and validation; the model may propose only
semantic content for the next snapshot. Every question must also permit the
user to reject all listed alternatives rather than forcing a false choice.

The repository's fixture tests establish the transition protocol, including
successor snapshots, explicit reassessment, abstention and turn limits. They
are not evidence that Bonsai has produced the intended readings. Real Bonsai
runs are recorded separately with provider, prompt and transport diagnostics;
an incomplete, timed-out or schema-invalid case is not a semantic pass or
failure. Until a reproducible evaluation runner scores the full corpus, this
file must not be read as claiming that the dialogue corpus has been passed.

The corpus is currently an evaluation fixture. It is loaded and checked for
oracle isolation by unit tests, but it is not silently folded into the ordinary
unit-test verdict tables. A real Bonsai run is recorded separately with the
provider, prompt and transport diagnostics intact.

## Reproducible sequential runner

The repository includes an offline runner that visits every corpus case with
one worker and writes a manifest plus one receipt per case:

```text
python -m onto4.cli.main eval-corpus \
  --corpus eval/clarification/epistemic-ontology-v1.yaml \
  --receipt artifacts/epistemic.receipts.jsonl \
  --report artifacts/epistemic.report.md
```

The receipt records only case identity, case mode, typed protocol outcome,
timings and safe run metadata. It does not store utterances, hidden oracle
fields, raw model payloads or credentials. Operational outcomes such as
transport, timeout, JSON, schema and provenance failures are kept separate
from semantic outcomes; none is converted automatically into `T`, `F`, `U` or
`C`. The offline fixture run therefore establishes corpus coverage and report
reproducibility, not semantic fidelity.

At present `eval-corpus` selects only this offline fixture executor. It does
not contact Bonsai or any other model-backed endpoint. A real provider run
requires a separate case executor with the same single-flight, manifest and
receipt contracts.

## Typed AST and the DSL experiment gate

The current formalization boundary keeps the typed JSON AST. A second
function-like DSL parser is intentionally not part of the first model-backed
loop.

The staged diagnostics must first show that nested AST serialization is the
dominant failure mode. Transport timeouts, invalid JSON, schema violations and
provenance failures are separate classes and must not be attributed to the
AST without evidence.

The DSL experiment may be opened only when a repeated diagnostic corpus run
shows an AST-specific failure pattern after transport, schema and provenance
issues have been isolated. Any such experiment must remain an opt-in adapter,
parse into the same typed AST, preserve the same fail-closed validation, and
leave the production provider contract unchanged until comparative results
justify promotion.
