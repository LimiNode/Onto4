# Profile-relative adjudication basis

This research-only note defines the first concrete basis for the two bounded
cases used by PR #40. It answers a narrower question than the structural
binding protocol and the receipt protocol:

> Did the successor preserve the commitment that this particular clarification
> was meant to make explicit?

The basis does not decide whether that commitment is true in universal Onto4
semantics. It checks preservation relative to a named case profile.

## Why a profile is needed

Suppose the host asks whether sharing a genome makes two people one person and
the answer fixes the intended reading as numerical identity. A successor may
keep the target ID while discussing genes as an inherited property, or while
asserting that a shared genome is sufficient for identity. The ID and the
prose can both be present, but the clarification has not been preserved.

The time case has the same shape. The answer fixes an observer-independent
present as the intended commitment. A successor that discusses only the order
of observations may retain the target while dropping that commitment. A
successor that explicitly rejects an observer-independent present contradicts
the profile, even though that rejection could be a meaningful position in a
different profile.

The adjudication basis therefore evaluates normalized commitments supplied by
an independent host-side procedure. It does not classify provider text and it
does not treat the provider's confidence as evidence.

## Frozen profiles

The implementation in `onto4.pipeline.semantic_basis` defines two versioned
profiles. Each criterion is a commitment that the successor must affirm.

| Profile | Target | Required commitments |
| --- | --- | --- |
| `genome-identity-bounded` v1 | `ambiguity-genome` | the identity criterion is numerical; a shared genome is not sufficient; distinct persons can share a genome |
| `intrinsic-time-bounded` v1 | `ambiguity-present` | the present is observer-independent; sequence order alone is not the present |

These are preservation criteria, not claims that either profile is the
canonical Onto4 answer. In particular, the second profile records the user's
observer-independent-time commitment; it does not silently turn that
commitment into observer-independent time in the modeled system.

The profile's canonical JSON description has a SHA-256 digest. The digest
identifies the exact criterion set used by a receipt and prevents a later
change to the rubric from being presented as the same basis.

## Decision rules

The host supplies one normalized state for each criterion:
`affirmed`, `denied` or `unspecified`.

- `verified`: every required commitment is `affirmed`;
- `contradicted`: at least one required commitment is `denied`;
- `unverified`: no commitment is denied, but at least one required commitment
  is `unspecified`;
- `not_comparable`: the evidence is absent, malformed, contains an unknown
  commitment, or names another case, target or relation.

Contradiction takes precedence over missing evidence. This keeps an explicit
semantic reversal distinct from a lack of adjudicator evidence.

The evaluator does not emit an Onto4 `T`, `F`, `U` or `C` verdict. Its
`verified` result means only that the normalized evidence satisfies this
versioned, profile-relative preservation test.

## Boundary and non-goals

The basis is deliberately separate from PR #41's receipt provenance checks.
The receipt protocol establishes which transition and which trusted basis a
receipt refers to. This module defines what one selected basis requires; it
does not establish that the adjudicator is competent or that the basis is
philosophically correct.

It also does not parse provider prose, infer commitments from lexical overlap,
rewrite snapshots, admit a successor, or run a model. A malformed or
profile-mismatched evidence record cannot produce `verified`.

The deterministic tests cover both profiles and all four decisions, including
cross-profile reuse, missing criteria, explicit contradiction, unknown
commitments and malformed envelopes. No new Bonsai run is part of this stage;
the earlier PR #40 receipts remain unchanged and their semantic identity stays
`unverified` until a separately reviewed adjudication record is produced.

## Next experiment

The next bounded experiment may use these frozen profiles to create independent
normalized evidence for the two existing transitions. That experiment must
publish the basis digest and the provenance of the normalization procedure
without exposing private oracle content. Passing this deterministic contract
alone is not such an experiment and does not upgrade historical receipts.
