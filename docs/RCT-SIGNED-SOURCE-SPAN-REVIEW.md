# Signed source-span obligation review (RCT research)

This adapter uses the **existing QualityRag Ed25519 signed-policy and signed-observation formats** to bind an exact source-span obligation inventory to a reviewed ConstraintIR policy.

The review covers the exact source/candidate text digests, obligation-inventory digest, source-span audit fingerprint, structural lens fingerprint, and every reviewed PackSpec node ID. The review must explicitly acknowledge **finite scope**, and the trusted reviewer key must be independently configured from the governing policy key ID. The verifier uses the host's durable nonce-replay service.

The review artifact is generated as a **draft** by `proposed_inventory_review`; the host/reviewer must inspect its contents and sign it externally before calling `verify_inventory_review`.

## Guarantees

- Altered source, candidate, inventory or joined receipt identity makes the signed review inapplicable.
- A changed governing ConstraintIR or different policy signature cannot silently reuse the old review.
- Replay, revoked reviewer key, changed review body, and over-broad completeness claims are rejected.
- A reviewed inventory with explicit contradictory source-span obligations returns `REFUSE`; other outcomes remain `INCONCLUSIVE`.
- The adapter never returns `ADMIT` or enables generation.

## Important non-guarantees

A verified reviewer signature proves the configured signer signed a particular **claim inventory**. It is **not** proof that the inventory includes every important nuance, that the supplied values reflect their original sentence meaning, that distinct original documents are independent, or that a proposed omission is safe.

The canonical APX G1–G12 source-span classifier and independently measured adversarial false-negative rates remain separate work; this adapter is not a substitute. No automatic extractor has been introduced.

## Test

```bash
python -m unittest discover -s tools/semantic_store/tests -p test_rct_signed_span_review.py -v
```

- `tools/semantic_store/rct_signed_span_review.py`
- `tools/semantic_store/tests/test_rct_signed_span_review.py`

Tests use real Ed25519 signatures and a durable SQLite nonce store, not a mocked verifier.
