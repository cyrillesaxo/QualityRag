# RCT v1.9 — signed primary-source custody

**Experimental implementation; no semantic admission.** This milestone expands signed witness lineage (v1.8) by verifying that exact supplied primary-source bytes match a separately attested source manifest. It reuses the existing canonical `signed_bundles.verify_attestation` mechanism and durable nonce contract. No alternate signature scheme was introduced.

## Inputs and policy separation

- Existing signed ConstraintIR policy and exact signed witness/observation records from v1.8.
- A **second signed attestation**, produced by a different configured custodian key ID, whose observation body contains `custody_roots`.
- A caller-supplied bounded map of exact raw primary-source bytes, keyed by declared root IDs.
- An attested manifest record per root: `root_id`, `source_ref`, `content_sha256`, `content_length`.
- A durable nonce-acceptance service and separate attestor / custodian public-key trust maps.

For each root, the verifier checks the bytes' SHA-256 and length, source reference, complete root inventory and no contradictory aliases. Identical byte digests are reported as shared-content root groups, even when labeled origins differ.

Signed records are bound to the same reviewed policy signature, service, environment, validity period and replay-checking mechanism as the existing QualityRag signed-observations implementation. A custodian key ID must be present in its separately configured trust map.

## What passing establishes

Only this narrow statement: *a configured custody key signed a manifest whose recorded SHA-256 matches the supplied bytes, and the record passes the existing attestation validation*. It does not authenticate the real-world author, completeness, correctness, original custody, semantic entailment, or distinct origin of two nonidentical documents.

V1.8 lineage checks still run afterward. A shared ancestor is a positive dependency signal; different source bytes are **not** evidence of independence. Explicit contradictions still REFUSE, otherwise the aggregate remains INCONCLUSIVE and `can_generate: false`.

## Failure tests and limits

The test suite rejects changed source bytes, omitted primary roots, changed source references, untrusted custodian keys, key-ID overlap between custody/evidence attestors, changed witness lineage, repeated signed attestations, and contradictory claims. Root aliases pointing to different source references fail closed.

The two required attestations are verified sequentially against a replay ledger; **nonce consumption is not atomic across both attestations**. A failure after accepting the custody nonce can consume it without producing a receipt. Clients should create a fresh attestation/nonce to retry; replay guard state must persist durably.

No source bytes are emitted in the receipt. A content hash is not a proof of domain truth, nor is this a general source crawler. The maximum supplied source size is 2 MB per root with at most 200 declared witness records.

## Reproduce

```bash
python -m pip install 'cryptography>=44,<47'
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

- `tools/semantic_store/rct_source_custody.py`
- `tools/semantic_store/tests/test_rct_source_custody.py`

## Next milestone

Link verified-bytes custody to authenticated original publishers/authoritative systems and an independently reviewed source-to-Purpose/PackSpec semantic map. Introduce actual FF-RCT reconstruction checks and adversarial completeness witnesses; do not equate successful cryptographic checks with authority to omit consequential information.
