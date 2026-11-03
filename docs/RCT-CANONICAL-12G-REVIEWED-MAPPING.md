# Canonical APX 12G reviewed coordinate projection

This research integration **reuses the exact G1–G12 code namespace** defined in the canonical APX module `cyrillesaxo/apx/packages/apx-rcoc/src/canonical-taxonomy.ts`. It **does not** infer that QualityRag's local source-span categories (NEGATION, CONDITION, etc.) are equivalent to an APX G coordinate, nor does it conflate canonical 12G with the separate KBCT K/B/C/T axes.

## Semantics

The authoritative canonical APX names and meanings are:

| Code | Canonical name | Purpose |
| --- | --- | --- |
| G1 | Label | Wording and lexical identity |
| G2 | Node | Semantic entity or target identity |
| G3 | Boundary | Limits, thresholds and validation |
| G4 | Edge | Transitions and relations |
| G5 | Operation | Actions and their effects |
| G6 | Perspective | Actor, viewpoint and access |
| G7 | Granularity | Scale and information density |
| G8 | Evidence | Confirmation and proof state |
| G9 | Prerequisite | Conditions and required state |
| G10 | Conflict | Contradictions and competing actions |
| G11 | Temporal | Timing, expiry and ordering |
| G12 | Authority | Origin, delegation, ownership and approval |

These labels are reference descriptions taken from the original APX taxonomy; **the code does not automatically classify source content**.

## Cryptographically reviewed mapping

`tools/semantic_store/rct_reviewed_12g.py` requires an explicit mapping of all 12 G coordinates:

```json
{"code":"G3","observed":true,"obligation_ids":["reviewed-exception"]}
```

Every source-span reviewed obligation must be mapped to one or more coordinates. A coordinate marked `observed=false` cannot contain obligation IDs and is rendered **UNOBSERVED**, never `NOT_APPLICABLE`. This prevents the absence of evidence from being misreported as a proof of irrelevance.

The source-span inventory, exact source/candidate document hashes, typed obligation-review identity and governing ConstraintIR policy are bound into a separately signed G review, requiring a distinct configured reviewer key from the governing policy signer and source-span reviewer. Signatures and one-use nonces are checked with the canonical QualityRag `signed_bundles` and durable ledger.

An observed source-span contradiction propagates to a G coordinate as `OBSERVED_VIOLATION` and produces `REFUSE`. No observed violation yields `INCONCLUSIVE`, not ADMIT.

## RCOC interface

The adapter **does not emit an APX RCOC snapshot**. Instead it returns `canonical_rcoc_snapshot=null` and `rcoc_snapshot_status=BLOCKED_UNKNOWN_APPLICABILITY_AND_UNMEASURED_DISPLACEMENT`.

This is a necessary semantic distinction: original APX RCOC interprets `applicable=false` as **NOT_APPLICABLE**, whereas an unobserved G coordinate is **UNKNOWN**, not proven inapplicable. The current inventory also lacks measured `deltaRef` displacement. Constructing a canonical RCOC input from the current finite source-span observations would invent both applicability and measurement.

A future input must independently establish which G coordinates are applicable, provide measured evidence-bound distances and an explicit transformation order before invoking canonical RCOC. No semantic movement or improvement is claimed in the meantime.

## Run

```bash
python -m unittest discover -s tools/semantic_store/tests -p test_rct_reviewed_12g.py -v
```

The tests exercise real Ed25519 policy/source-span/G-review signatures, durable replay checks, coverage of all twelve coordinates, missing or remapped obligations, forged reviewer identity and original-source policy substitution.

## Unresolved research claims

- Canonical G classification cannot be inferred automatically from local semantic source-span types.
- A human-reviewed map is a signed *assertion*, not open-world completeness proof.
- Source authority, classifier recall/precision, D15 deceptive witnesses, RCOC movement metrics, native FF-RCT and semantic ADMIT remain unestablished.
- No original source text, HMAC fingerprint, or authentication key is embedded in the G snapshot.
