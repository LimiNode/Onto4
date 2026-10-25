# PR #60 — independent semantic verification protocol

PR #60 is protocol/design work only. It introduces no provider call, no
production authority and no `SemanticAdjudicationReceipt`.

The verifier compares a frozen host-owned semantic expectation with a
host-normalized observation. Provider self-reports are deliberately ignored.
The deterministic matrix distinguishes:

- same semantic target with the same identifier;
- same semantic target with a different identifier;
- wrong semantic target with the expected identifier;
- genuine ambiguity resolution backed by required evidence;
- ambiguity merely omitted;
- indeterminate semantic relationship.

Literal identifier retention, semantic target alignment and ambiguity resolution
are recorded as separate measures. A matching identifier can therefore still be
semantically incorrect, while a different identifier can remain semantically
correct. Omission and indeterminate evidence never become a positive semantic
result.

This protocol is not a production adjudicator and is not connected to admission
or workflow decisions. A future model-backed experiment must supply independently
prepared expectations and blinded host-side normalization before any semantic
claim is made.
