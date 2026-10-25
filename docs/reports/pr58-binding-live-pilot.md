# PR #58 — bounded provider target-binding pilot

This report records one bounded live run of the research-only target-binding
protocol. It is not a semantic evaluation: no independent oracle was available,
so every semantic result is `not_evaluated` and the aggregate is
`not_comparable`.

## Reproducibility

- source SHA: `8450d2ffe4bd09642426d8777f99b1eb0f52e0a1`
- protocol: `pr56-target-binding-v1`
- pilot: `pr58-binding-live-pilot-v1`
- run identifier: `pr58-20261025-bounded-001`
- model artifact digest: `null` (the endpoint did not provide one)
- backend: llama.cpp OpenAI-compatible `/v1`
- conditions: A, B, C, in that order
- scenarios: two frozen public aliases, one call per cell
- sampling: temperature `0`, max output `1024`, thinking disabled

Raw prompts, answers, provider payloads, private target identifiers and local
paths are intentionally absent from this report and the JSON receipt.

## Observed technical outcomes

| condition | valid cells | literal target retained | notes |
|---|---:|---:|---|
| A — full snapshot | 2/2 | 0/2 | schema, catalog and lineage checks passed |
| B — explicit binding | 2/2 | 2/2 | schema, catalog and lineage checks passed |
| C — minimal target-focused envelope | 0/2 | unknown | both calls ended in schema failure |

The result supports only a bounded technical observation: the explicit binding
protocol retained the host target identifier in both observed cells, while the
full-snapshot protocol did not. The C failures do not establish a semantic
failure; they establish that this particular target-focused response envelope
was not produced in schema-valid form in either cell.

No claim is made that identifier retention demonstrates semantic understanding.
The run produced no independent semantic evidence and no
`SemanticAdjudicationReceipt`.

## Safety and limits

The pilot executed exactly six provider calls and was not repeated. Production
admission and semantic adjudication authority were unchanged. Historical
receipts remain untouched. The evidence is insufficient to choose a production
architecture; the next step is host-side semantic verification research or a
better-specified target-focused protocol, not promotion based on identifier
retention alone.
