# Signed D15 witness-record binding — research-only

This feature connects the original APX deceptive-witness 3 × 5 diagnostic to the **canonical QualityRag Ed25519 policy/observation signature format**. It authenticates the precise declared evidence IDs and record hashes a reviewer signed; it does **not** independently prove the underlying observations, completed probes, source independence or semantic meaning.

## Execution contract

Use `tools/semantic_store/rct_signed_d15.py`:

1. Run the separately compiled **original APX** `buildDeception15Gate` through `rct_apx_deception_native.mjs`, obtaining a native diagnostic.
2. Construct a version-bound inert `proposed_d15_review` with: exact source/candidate SHA-256, reviewed PackSpec ConstraintIR, all 15 canonical cell IDs and statuses, each cited evidence ID and its host-supplied record SHA-256.
3. Have a separately configured authorized D15 reviewer inspect and sign the exact `d15_review` payload through `signed_bundles.sign_attestation`, bound to the independently signed governing PackSpec policy.
4. Call `verify_d15_review` with trusted policy and reviewer public keys, pinned minimum policy sequence, service/environment, as-of timestamp, and a **durable nonce guard**.

The verifier rejects changed source/candidate digests, missing or additional evidence-record IDs, substituted evidence SHA-256s, duplicate cell IDs, inconsistent native status lists, fabricated ADMIT, changed policies, revoked reviewer keys, and replay.

PASS and FAIL cell declarations must cite specific evidence-record IDs. UNTESTED stays UNTESTED. A full **claimed** pass remains `INCONCLUSIVE`; no FF-RCT compression or generation can be authorized.

## What the signature proves — and does not prove

A valid signature proves a configured trusted key approved that exact finite set of claims and evidence-record digests. **It does not prove** the reviewer correctly inspected the original source, that the APX executable was independently attested, that the host's supplied evidence digest was produced from valid original bytes, or that independent probes demonstrated that a deceptive-witness cell passed.

The API deliberately reports:
- `source_authority=NOT_ESTABLISHED`
- `independent_evidence_custody=NOT_ESTABLISHED`
- `deception_probe_execution=NOT_ATTESTED`
- `semantic_completeness=UNKNOWN`
- `qualityrag_admission=INCONCLUSIVE`
- `compression_authorized=false`
- `can_generate=false`

Any explicitly failed cell yields the diagnostic verdict `REFUSE`. These semantics are stricter than the canonical APX local gate's possible `ADMITTED` result.

## Strict exact-byte variant

`verify_d15_review_with_bytes` additionally accepts a bounded map of **actual evidence-record bytes** for every cited D15 reference. It verifies each record's SHA-256 and inventory completeness **before** validating the review signature and consuming the one-use nonce. A substitution or missing record fails immediately without spending the nonce; a later retry with the correct bytes remains possible.

Its resulting `submitted_evidence_content_integrity=VERIFIED_SHA256_MATCH` means that the provided bytes match the reviewer's signed hash inventory. It does **not** mean the bytes were captured from an independent original publisher, that their declarations are true, or that the adversarial probe was actually run. The fields `independent_evidence_custody=NOT_ESTABLISHED` and `deception_probe_execution=NOT_ATTESTED` are therefore unchanged.

## Verification

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_rct_signed_d15.py' -v
```

The tests exercise real Ed25519 signing and durable nonce replay, including source substitution, evidence-reference substitution, all-15-passed non-admission, duplicate inventory rejection, policy rollback and explicit failure dominance.

The original native APX engine must still be executed separately through the read-only private APX workflow before any claim of native-parity success. Any independent source-custody gate must bind the exact evidence-record SHA-256s to authentic bytes and an independently verified authority, and must not be replaced by this review signature.

## Next acceptance criterion

Join this signed D15 diagnostic with independently verified source-byte custody and executable deceptive-witness probes. Require each PASS to have an authenticated, purpose-relevant probe result and independently assessed provenance. Preserve untested/unknown as unknown, regardless of any caller's signed assertion.
