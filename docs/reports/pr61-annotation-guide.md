# PR #61 annotation guide

This guide is a compact operational rubric for a blinded reviewer. The
reviewer sees the initial interpretation, the host-issued clarification, the
intended target description and the proposed successor. The reviewer does not
see condition names, model name, target-ID equality, binding verdicts, other
reviewers' answers or the research hypothesis.

## Target alignment

- `aligned`: the successor addresses the same semantic target and preserves
  the distinction requested by the clarification.
- `misaligned`: it answers a different question, substitutes a related but
  distinct object, or imports an unsupported ontology.
- `indeterminate`: the successor is too vague or contradictory to decide
  without an additional assumption.

Changing a technical identifier is not itself misalignment. Keeping one is not
evidence of alignment.

## Ambiguity resolution

- `resolved`: the successor explicitly selects or explains the intended
  reading and removes the relevant competing reading.
- `not_resolved`: it addresses the topic but leaves the requested ambiguity
  open, or answers a different target.
- `merely_omitted`: the ambiguous expression disappears without a justified
  choice; deletion is not clarification.
- `indeterminate`: the available text supports incompatible readings.

## Evidence sufficiency

- `sufficient`: the visible material supports the label without relying on a
  hidden model claim or unstated ontology.
- `insufficient`: relevant context or evidence is missing.
- `contradictory`: the material supports incompatible claims.
- `not_available`: no admissible evidence is available for a semantic call.

## Abstention

Use the abstention field whenever any required distinction cannot be decided.
Record a short reason and, where possible, references to the relevant text
spans. Do not turn uncertainty into a majority-vote truth. Disagreements remain
visible as raw judgments; adjudication is a separate, explicitly recorded
step.

The machine-readable shape is
`docs/reports/pr61-annotation-schema.json`. Raw responses and reviewer notes
must remain in an approved private store; public artifacts contain aliases,
aggregates and provenance only.
