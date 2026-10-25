# PR #62 — blinded annotation and evidence boundary

PR #62 adds a small research-only instrument on top of the frozen PR #61
protocol. It creates reviewer packets that contain the semantic material needed
for a judgment while omitting condition names, model identity, target-ID
equality and binding verdicts. Technical identifiers are represented only by a
neutral alias. The packet ID and content digest are bound to the complete
packet content, so an old annotation cannot be applied to changed content.

Annotation records are immutable, version-bound to the packet and rubric, and
carry explicit alignment, ambiguity-resolution and evidence-sufficiency labels.
Confidence is recorded separately from the labels. Abstention requires a
reason. Raw payloads and private notes are not emitted by this module.

Reviewer disagreement remains visible as raw judgments with agreement flags.
The comparison helper never turns a majority into semantic truth and never
performs hidden adjudication.

Host evidence has a separate verification boundary. An attestation is allowed
only when a host-controlled registry confirms reviewer identity and
independence, packet assignment, exact annotation digest, source, normalizer
and evidence checks. Caller-supplied stage labels, aliases and provider
payloads are explicitly rejected. The resulting attestation is research
metadata, not an independent semantic oracle or a production
`SemanticAdjudicationReceipt`.

No Bonsai calls are made by this PR.
