# Public parity roadmap

## Shipped in initial PR
- Cross-language PackSpec v0.1 field contract
- Evidence source reference, origin independence, freshness
- Conservative admission/refusal/inconclusive decision
- Runnable tests and a Python demonstration

## Not shipped / do not claim
- Complete APX PackSpec v3 semantics and canonical 12G taxonomy
- Full D15 deception census across DW / DD / DS × 5 axes
- WitnessGraph dependency graph beyond origin deduplication
- W_min minimal witness proof, HCR recovery, TERM replay, RCOC semantic drift
- Cryptographically signed receipts, policy registry, remote verifier, server API
- Source authenticity verification or RAG runtime integration

## Acceptance gates for future releases
1. Freeze and version schema with conformance vectors covering malformed inputs.
2. Execute the same fixtures in Java/Python/TS; require identical normalized decisions.
3. Port each APX subsystem with golden parity tests, independent code/security reviews and license checks.
4. Evaluate real-world multi-hop RAG queries with adversarial counterexamples and recorded failure analysis.
5. Add Spring Boot starter, FastAPI middleware, retrieval adapters, CLI and hosted playground.
6. Publish package releases only after CI matrix and supply-chain attestation.

Never copy credentials, proprietary customer data, private repo metadata, or confidential examples into this public repository.
