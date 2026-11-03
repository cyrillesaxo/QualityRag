# RCT signed derivation lineage v1.8 — experimental

This milestone reuses the repository's existing **Ed25519 signed policy** and **signed observation** contracts, with durable nonce replay prevention, to bind versioned RCT lens metadata to witness derivation records.

The module lives in `tools/semantic_store/rct_signed_lineage.py`; the tests are in `tools/semantic_store/tests/test_rct_signed_lineage.py`.

## Operation

1. Verify the signed reviewed ConstraintIR policy via `tools/packspec_compiler/signed_bundles.verify_policy`. Trust keys, service/environment, validity interval and minimum sequence come from the host.
2. Require the signed observations to contain the exact lens fingerprint, graph-source SHA-256, evidence PackSpec digest and WitnessGraph mapping fingerprint.
3. Verify signed records using canonical `verify_attestation`, including the matching policy signature, nonce, service/environment, timestamp and equality of evaluated witnesses and observations. The durable nonce store is supplied by the host; the tests use `signed_gate.SQLiteNonceStore`.
4. Construct a bounded derivation DAG using each witness's explicit `derives_from` witness IDs. Reject duplicate IDs, missing ancestors, cycles, self-dependency and oversized input. Leaf witnesses are *declared* primary sources.
5. Compute the transitive declared root origins of each supported witness. Collapse supporting witnesses with overlapping roots into the same connected component, even if their immediate origin labels differ.
6. Reuse v1.7's canonical unified-gate and SDK WitnessGraph receipts, and add lineage-root coverage diagnostics; preserve `REFUSE` and otherwise return `INCONCLUSIVE`. **Generation remains disabled.**

## Important trust and epistemic boundaries

Cryptographic verification proves that a configured trusted key signed a particular record, **not** that the record's source description, chain of custody, or claim is true. The ancestry graph is also signer-asserted metadata. Different root identifiers cannot be accepted as independent source custody without external provenance checking. Therefore:

- Shared roots provide evidence of *dependency*.
- Distinct roots provide only an *unverified claim of independence*.
- A fully signed batch is still not authorization to omit an RCT distinction.
- The legacy evidence-pack projection and signed reviewed ConstraintIR are not proven to originate from the same governing source; no authorization is inferred from joining them.
- PackSpec semantic sufficiency, APX HCR/RCOC/WBC and FF-RCT reconstruction have not been established.
- The research adapter is diagnostic: it never calls a generator or returns `ADMIT`.

## Reproduction

The Semantic Store workflow installs the existing `cryptography>=44,<47` dependency.

```bash
python -m pip install 'cryptography>=44,<47'
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

The tests include shared-parent collapse, independent-looking labels, real Ed25519 signature verification, exact lens binding, missing parents, cycles, tampering, durable replay protection, explicit contradictions and fail-closed admission.

## Next acceptance requirement

Have independently verifiable original-source custody and signing authority associated with a semantic obligation, not just a signed witness batch. Then evaluate whether the underlying PackSpec truly authorizes the omitted distinctions and whether its original source semantics were preserved. Preserve the ability to reconstruct full information through actual FF-RCT, with separately measured loss and work.
