# Concepts and API reference

## PackSpec v0.1

`pack.id` and `pack.version`: required nonempty strings; `requirements`: nonempty ordered array; `requirements[].id`: unique nonempty string; `min_independent_sources`: positive integer (defaults to 1); `max_age_seconds`: optional nonnegative integer. See [JSON schema](../contracts/qualityrag.schema.json). Extra fields in that schema are not supported.

## Evidence metadata

Required fields are `id`, `requirement_id`, `origin`, `source_ref`, `status`, `observed_at`. Supported statuses: `SUPPORTS`, `CONTRADICTS`, `UNKNOWN`. Timestamps should be explicit-offset RFC3339/ISO8601 strings; UTC `Z` is safest. Independent evidence is approximated by the number of **distinct supplied origin identifiers**, not the number of documents.

## Decisions

- `ADMIT`: all requirements have enough non-stale supporting origins, no in-scope contradictions, under submitted metadata.
- `REFUSE`: a non-stale, governing contradictory witness was supplied; dominates all other findings.
- `INCONCLUSIVE`: missing, stale, future, unknown or insufficient evidence; does not imply falsehood.

The output includes `schema`, `pack_id`, `pack_version`, `verdict`, and per-requirement `findings` with `reasons` and `independent_sources`. Reason codes include `CONTRADICTION`, `INSUFFICIENT_INDEPENDENT_EVIDENCE`, `INVALID_EVIDENCE`, `UNKNOWN_EVIDENCE`, `STALE_EVIDENCE`, and `FUTURE_EVIDENCE`.

## Extended experimental compiler

In Java, Python and TypeScript only, the compiler adds requirement `scope` and `authority` labels (default scope `global`), `constraint_ir`, a `witness_graph` with declared-origin dependent groups, and `wgap` with unresolved obligations. Additional reason codes include `SCOPE_MISMATCH`, `AUTHORITY_MISMATCH`, `INVALID_WITNESS`. Do not assume that labels authenticate origins or authoritative institutions. The extended compiler API is separate from the original v0.1 evaluator.

## Threat model / non-claims

A malicious client can invent witnesses and origin strings. Only trusted server-side collectors may provide evidence; enforce document access controls upstream. QualityRag does not extract text, independently verify truth, perform DLP, or certify regulatory compliance. `ADMIT` is not permission for an unsafe action and does not guarantee a correct AI response.

## Runtime libraries

The SDKs are checked in as source modules and have language-specific build tooling. No package registry publication is claimed. For a versioned API contract, pin the repository commit and review breaking changes before updating.
