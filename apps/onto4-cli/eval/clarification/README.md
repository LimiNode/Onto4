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
