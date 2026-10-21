# Independent Evidence Normalization

This research-only stage asks a practical question left open by PR #42: can
the published, redacted evidence from PR #40 support an independent
normalization of semantic commitments?

The answer for the two existing public pilot artifacts is no. They report
structural outcomes — such as whether a target ID was present and whether a
binding claim was admissible — but deliberately omit the successor content,
the exact transition snapshot IDs and any normalized commitments. Those
omissions protect the original model material; they also prevent a later
reviewer from reconstructing semantic evidence honestly.

The recorded result is therefore `insufficient_evidence`, not `verified` and
not a negative semantic judgment. The assessment and SHA-256 digests of the
two inspected artifacts are published in
`pr43-independent-evidence-normalization-assessment.json`. No historical
receipt has been changed. The digest uses UTF-8 text after CRLF is normalized
to LF, so its value does not depend on the checkout platform.

## A record for a future independent normalization

`onto4.pipeline.semantic_normalization` defines the narrow public envelope a
future normalizer must supply. It contains:

- the case, previous and current snapshot IDs, host question, target and
  relation of one binding transition;
- exact answer IDs and the SHA-256 digest of the selected profile-relative
  basis;
- a normalizer identity and version, plus an opaque SHA-256 digest of the
  source material it reviewed;
- only normalized `affirmed`, `denied` or `unspecified` commitments.

Raw provider text, prompts and private oracle material are not fields in that
envelope. An opaque source digest records which material an independently
trusted normalizer inspected; the digest does not itself establish the
material's meaning.

Before using the commitments, the host checks that the record belongs to the
same structurally admissible binding claim and host-issued transition, uses
the selected `basis_digest`, arrived through an attested trusted-normalizer
channel, and names an actor other than the provider. It then applies the
profile-relative basis from PR #42.

The resulting `verified`, `contradicted` or `unverified` value is still only
the decision of that versioned basis. It is neither a universal Onto4
semantic verdict nor a replacement for the separate adjudication receipt
protocol from PR #41. In particular, this module does not issue a receipt and
does not alter successor admission.

## Boundaries

The implementation does not parse a provider's prose, infer commitments from
a target ID, or turn the PR #40 summaries into evidence. A malformed record,
a mismatched transition or basis, an unattested source, an untrusted
normalizer, or a normalizer identical to the provider fails closed as
`not_comparable`.

For a later bounded experiment, the host would have to preserve the required
transition provenance and authorize an independent normalizer to inspect the
non-public source material. It may publish that normalizer's provenance,
source digest and normalized commitments, but not the private material itself.
Only after a separately reviewed policy decision could a valid normalization
record be used as input to a PR #41-style adjudication receipt.
