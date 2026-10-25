# PR #60 — independent semantic verification protocol

PR #60 is protocol/design work only. It introduces no provider call, no
production authority and no `SemanticAdjudicationReceipt`.

The verifier compares a frozen host-owned semantic expectation with an
observation carrying an explicit provenance boundary: observation identity,
normalizer identity/version, source identity, authority and evidence status.
Provider self-reports are deliberately ignored. The current matrix is labelled
`synthetic_oracle_fixture`; its `correct` rows demonstrate verifier mechanics,
not semantic truth about Bonsai output.

Evaluation has two explicit modes. `synthetic_fixture` preserves deterministic
fixture mechanics. `real_observation` is the default and cannot return a
positive semantic result unless a separate `TrustedHostEvidenceResolver`
attests the exact relationship among expectation, observation, normalizer,
observation source, evidence sources, statement keys and the canonical digest
of the complete normalized observation. Caller-supplied `HOST_INDEPENDENT` or
`VERIFIED` labels alone therefore fail closed. The attestation set is
host-maintained research input and must be established separately from the
provider observation; the resolver does not create an independent semantic
oracle by itself. Invalid verification modes are rejected before any semantic
evaluation.
The deterministic matrix distinguishes:

- same semantic target with the same identifier;
- same semantic target with a different identifier;
- wrong semantic target with the expected identifier;
- genuine ambiguity resolution backed by required evidence;
- ambiguity merely omitted;
- indeterminate semantic relationship.

The negative-control matrix also covers provider-only claims, missing normalizer
provenance, duplicate evidence sources, contradictory evidence and apparent
resolution without admissible evidence.

Literal identifier retention, semantic target alignment and ambiguity resolution
are recorded as separate measures. A matching identifier can therefore still be
semantically incorrect, while a different identifier can remain semantically
correct. Omission, indeterminate evidence, missing normalizer provenance,
provider-controlled evidence and contradictory sources never become a positive
semantic result.

This protocol is not a production adjudicator and is not connected to admission
or workflow decisions. A future model-backed experiment must supply independently
prepared expectations and blinded host-side normalization before any semantic
claim is made.
