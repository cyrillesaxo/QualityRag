# Canonical APX semantic-source comparator integration

The original semantic-source comparator lives in the separately authorized `cyrillesaxo/apx` repository:

- `packages/apx-epistemic/src/semantic-conversion.ts`
- `packages/apx-epistemic/src/semantic-source-spans.ts`

QualityRag **does not copy** the original implementation. The optional `tools/semantic_store/rct_apx_source_spans_native.mjs` bridge dynamically loads the original, separately compiled APX module and calls `inspectSemanticTextTransition`.

## Execution

The `.github/workflows/rct-native-apx-parity.yml` workflow was extended to sparse-checkout `packages/apx-epistemic` and compile just the original semantic-conversion/source-span TypeScript files using the original repository source, then run `test_rct_apx_semantic_spans_real.mjs`.

That native workflow is manual and requires the read-only `APX_REPO_READ_TOKEN` secret to access the original private repository. A normal QualityRag regression cannot substitute interface stubs or declare native validation passed. The normal CI *does* exercise missing-native-engine failure and module syntax.

The original engine takes source/candidate text, exact SHA-256 source-byte digests and a host-owned HMAC key (at least 32 bytes). The bridge passes those values to the original implementation, then exposes **only** the redacted result: decision, changed semantic kind/status, and the original conservative authority/coverage markers. It never emits raw source text, matched quotes, HMAC key or underlying fingerprints.

## Adversarial test cases

- Nursing: removing `NOT` from a medication instruction must produce an observed negation difference and `REFUSE`.
- HVAC: removing an `unless` condition must produce an observed scope difference and `REFUSE`.
- Driving: substituting a waiting period from 12 to 6 months must produce a numeric difference and `REFUSE`.
- Unchanged conditional refund wording remains `INCONCLUSIVE`, never `ADMIT`.
- An invalid HMAC key or missing compiled original APX engine fails immediately.

These are controlled synthetic adversarial examples, **not** a claim that the comparator can correctly interpret complete patient-care, licensing or legal instructions.

## Semantics and limits

The original APX engine uses **bounded English lexical patterns** and HMAC-protected candidate fingerprints. It is not a general source-to-meaning parser. Detecting a difference is useful evidence of potential drift; no difference is not proof that all important distinctions were preserved. Source authority, policy review, unknown exceptions, signed obligations and FF-RCT semantic reconstruction remain separate checks.

The two candidate evaluators serve different purposes:

- Python source-span inventory: external explicitly supplied typed obligations, optionally reviewed and signed.
- Original APX semantic-source comparator: candidate observations from bounded lexical patterns, with no externally authenticated authority.

For a future combined gate, a difference flagged by either evaluator should trigger a refusal or review; neither evaluator is authorized to assert complete meaning conservation or grant generation.


## Safe dual-check orchestration

`tools/semantic_store/rct_dual_semantic.py` provides `combine_semantic_diagnostics`. It joins the exact source/candidate SHA-256 digests from the bounded APX comparator and the source-span inventory, then **rechecks the original Ed25519 reviewer attestation** using the canonical signed PackSpec policy and durable nonce guard. A detached `review_signature: VERIFIED` flag is never trusted.

A malformed native payload is rejected **before the one-use reviewer nonce is consumed**. A mismatch of source or candidate digest fails closed. A REFUSE from either observed path dominates. If the original private APX engine was not run, its status remains explicitly UNAVAILABLE, not a synthetic pass.

This combined receipt is not an authenticated attestation of which APX executable ran. It preserves `NATIVE_RUNTIME_RESULT_NOT_INDEPENDENTLY_ATTESTED`; no ADMIT or generation is permitted. Tests use actual signed review verification while native payload interface fixtures remain distinguished from the opt-in original-APX execution tests.
