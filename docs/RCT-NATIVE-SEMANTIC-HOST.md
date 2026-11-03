# Native APX → QualityRag signed decision: trusted-host execution

**Implemented boundary:** `tools/semantic_store/rct_native_semantic_host.py` calls the original compiled `apx-epistemic` semantic-source comparator through `tools/semantic_store/rct_native_semantic_runner.mjs`, then passes the resulting redacted diagnostic to the canonical `rct_dual_semantic.combine_semantic_diagnostics` signed PackSpec reviewer gate.

This closes the previous *runtime orchestration* gap between a separate JS adapter and a Python governance decision. It does **not** prove semantic sufficiency or authenticate original publisher truth.

## Runtime contract

1. An authorized application host chooses a trusted, absolute `APX_PACKAGES_ROOT` containing the **original compiled** APX packages. Do not derive this path from an uploaded document or user request.
2. The host supplies bounded UTF-8 source and candidate texts (at most 8 KiB each). The submitted bytes are checked against the *exact source and candidate digests* bound into the signed reviewed source-span inventory before executing the native process.
3. Python creates a random 256-bit per-invocation HMAC key. It launches a separate Node process through bounded standard input and passes the key in a short-lived subprocess environment. It **does not forward inherited cloud credentials, GitHub tokens or arbitrary environment variables**.
4. The runner imports the original APX `inspectSemanticTextTransition` function. A missing or invalid original binary is a hard failure, never a mock fallback.
5. The native process prints **only** redacted semantic-kind/status changes, source/candidate SHA-256 digests, and conservative verdict flags. It suppresses raw excerpts, HMAC fingerprints and exception stacks.
6. The Python host checks the strict output shape, bounded size, original comparator schema, source/candidate digests, and invariants `source_authority=UNVERIFIED_HEURISTIC`, `semantic_completeness=UNKNOWN`, `can_generate=false`.
7. Only after native preflight does the dual evaluator validate the original signed reviewed PackSpec policy and reviewer attestation against a durable nonce guard. Contradictions cause `REFUSE`, otherwise `INCONCLUSIVE`; no source may generate on the basis of these checks.

## Interfaces

```python
from rct_native_semantic_host import execute_dual_semantic_check

receipt = execute_dual_semantic_check(
    joined=source_span_joined_candidate,
    source_text=original_document,
    candidate_text=transformed_document,
    apx_packages_root="/trusted/original/apx/packages",
    ir=reviewed_constraint_ir,
    signed_policy=signed_constraint_ir_policy,
    signed_review=signed_source_span_review,
    policy_keys=host_trusted_policy_keys,
    reviewer_keys=host_trusted_reviewer_keys,
    minimum_sequence=1,
    service="qualityrag-service",
    environment="test",
    as_of="2026-11-03T18:00:00Z",
    nonce_accepted=durable_nonce_acceptance_function,
)
```

All identifiers above except imported function names are illustrative variables, not ready-to-run secrets. Runtime and reviewer credentials must be provided by an authorized host.

## Reproducible checks

**Normal QualityRag CI** runs `test_rct_native_semantic_host.py`: input bounds, no-source fail-closed behavior, forged output rejection, no deployment-secret inheritance, and digest mismatch refusal before native invocation. The real native test module is skipped unless explicitly enabled.

**Private canonical APX parity workflow** (manual, read-only APX token required) additionally runs:

```bash
QR_REQUIRE_NATIVE_APX=1 APX_PACKAGES_ROOT=/absolute/original/apx/packages \
python -m unittest discover -s tools/semantic_store/tests \
  -p 'test_rct_native_semantic_host_real.py' -v
```

The real test compiles the original APX engine, then exercises actual Node-native semantic falsification, Python host execution, source-bound inventory, Ed25519 signed reviewed policy, and the durable SQLite nonce ledger. Nursing negation removal and HVAC exception removal must refuse. Identical text remains inconclusive.

## Integrity and deployment limitations

- This workflow only validates the native engine when an actual **authorized original APX checkout** is present. The standard CI cannot claim to have executed it.
- A trusted path does not cryptographically attest the native executable's origin. The private workflow separately records the exact APX source revision; a production host must pin and attest the original source/build artifact and verify its deployment environment.
- Host process credentials and logging policies remain the responsibility of the deployment environment. Source text travels within this host's process IPC and is not returned to model-visible responses; process memory cannot be considered zero-knowledge.
- The signed reviewer inventory may omit meaningful unobserved distinctions. A successful lexical check is **not** proof of semantic conservation.
- The two signed attestations in the wider research pipeline are not one atomic transaction. A failed later stage may consume one nonce.
- Production authenticated publisher evidence, field-level policy, privacy review, independent corpus evaluation and native FF-RCT remain separate acceptance requirements.

**Admitted status stays INCONCLUSIVE throughout this research API.**
