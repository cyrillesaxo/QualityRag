# Signed QualityRag policy bundles and evidence attestation

**Research lineage:** Cyrille Eloundou — https://apx.guide/.

This experimental implementation signs **typed ConstraintIR policies and exact evidence/observation records** for the Python unified gate. It does **not** authenticate real-world facts, source independence, or completeness of the underlying APX PackSpec.

## Security model

| Feature | Mechanism |
| --- | --- |
| Policy signing | Ed25519 and separate signature domain |
| Evidence signing | Ed25519, bound to exact policy signature |
| Canonical encoding | QR-CJSON-1, restricted sorted UTF-8 JSON without floats |
| Key selection | Explicit pinned public-key trust stores and key IDs |
| Binding | Service, environment, policy sequence, issued/expiry timestamps |
| Anti-rollback | Required minimum sequence supplied from host-controlled durable state |
| Anti-replay | Signed nonce accepted by atomic durable store |
| Guarded generation | Only after policy verification, metadata/semantic ADMIT, and attestation |

QR-CJSON-1 is **not RFC 8785/JCS**. It deliberately excludes floating-point JSON, duplicate keys, and noncanonical wire representations. This is a Python implementation and has **not** established interoperability with all ten SDK languages.

## Example integration

```python
from signed_gate import guarded_generate_signed, SQLiteNonceStore

result = guarded_generate_signed(
    signed_policy=policy_bundle,
    signed_observations=attestation,
    policy_keys=trusted_governance_keys,
    attestor_keys=trusted_measurement_keys,
    service="payments-api",
    environment="production",
    minimum_sequence=15,
    nonce_accepted=SQLiteNonceStore("/var/lib/qualityrag/used-nonces.sqlite"),
    witnesses=retrieved_witnesses,
    observations=measured_events_and_probes,
    as_of="2026-11-02T10:05:00Z",
    generator=lambda: chat_client.complete(prompt),
)
```

The actual `trusted_governance_keys`, `trusted_measurement_keys`, policy bundle and attestation are host-provided. Keep private keys in secure storage and sign policy promotions out of band.

**One-instance replay ledger:** SQLite persists nonces and rejects duplicate insertions. For multiple replicas, they must share a single transactional database or use a robust central nonce store; isolated node-local databases do not prevent cross-replica replay.

**Policy sequence floor:** Store and monotonically update a minimum accepted policy sequence on every approved deployment. A signature without an external floor does not prevent a valid old bundle from being replayed.

**Evidence trust:** The evidence signing key must belong to a trusted component that checks the actual source and measurement origin. A signature proves that the signing key signed these records, not that their claims are true, independent or complete.

**Failure behavior:** Missing/revoked keys, invalid policy signature, expiry or rollback stop evaluation with an exception. An invalid evidence attestation or nonce reuse produces INCONCLUSIVE and never invokes the generator. A declared but unsupported AUTHORITY/PREDICATE constraint also remains INCONCLUSIVE.

## Run tests

```bash
python -m pip install -r tools/packspec_compiler/requirements.txt
python -m unittest discover -s tools/packspec_compiler/tests -p 'test_*.py'
```

The new tests cover signature tampering, key rotation and role separation, valid-but-stale bundles, rollback, expiry, wrong service/environment, false attestation, replay across processes, malformed canonical input, evidence substitution and fail-closed generation.

**Remaining work:** authenticated signer workloads, managed private-key lifecycle, cross-language canonical serialization, distributed nonce state, signed promotion ledger and independent source custody verification.
