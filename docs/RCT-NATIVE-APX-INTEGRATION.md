# Real APX WBC / HCR / RCOC integration — native verification

The `rct_apx_native.mjs` adapter loads the *original*, separately built TypeScript engines from the private `cyrillesaxo/apx` workspace. It does not copy code or silently substitute implementations.

## Required verified path

The `Canonical APX Native Parity (private checkout)` workflow uses two independent GitHub checkouts:

1. Current QualityRag source.
2. Sparse checkout from the original private APX repository, scoped to `packages/apx-wbc`, `packages/apx-hcr`, and `packages/apx-rcoc`.

It builds those packages with a pinned TypeScript toolchain and executes `tools/semantic_store/tests/test_rct_apx_native_real.mjs`. The tests check actual WBC verdict-preserving removal; HCR authorized versus unauthorized hypothesis elimination; RCOC observed deterioration and stable snapshots.

The workflow records both source commit IDs. Native runtime tests are NOT the same as the transport/stub tests in the normal QualityRag CI.

## One-time GitHub setup

Create a repository secret named `APX_REPO_READ_TOKEN` in QualityRag that grants **read-only Contents** access to `cyrillesaxo/apx`. A fine-grained access token or properly scoped GitHub App installation token is sufficient. Do not use a token with write or administrator permissions. This secret is never printed or committed.

From the QualityRag Actions tab, select **Canonical APX Native Parity (private checkout)** and run it with `apx_ref=main`, or preferably an exact reviewed APX commit SHA. The action **fails** when the credential is absent or when the actual packages cannot compile. It never reports a green result by substituting mock packages.

Once the native workflow passes, its two source commit SHAs and run ID must be attached to the release review. Any APX dependency update must rerun the native workflow against the new source commit.

## Local reproduction

```bash
# In the original, separately authorized APX workspace:
npm ci --ignore-scripts
npx tsc -p packages/apx-wbc/tsconfig.json
npx tsc -p packages/apx-hcr/tsconfig.json
npx tsc -p packages/apx-rcoc/tsconfig.json

# In QualityRag with an absolute path to the APX packages directory:
APX_PACKAGES_ROOT=/absolute/path/to/apx/packages \
  node --test tools/semantic_store/tests/test_rct_apx_native_real.mjs
```

## Security and epistemic boundaries

- Both repositories remain private in their respective credential domains. No APX source is copied into QualityRag.
- The workflow does not expose APX source or contents as build artifacts.
- A passing native WBC check tests verdict preservation **for the supplied host oracle**. It does not certify source truth, witness authenticity or universal minimality.
- HCR remains a bounded registered-regime diagnosis. RCOC compares evidence-bound semantic snapshots, not raw world truth.
- This integration **never enables semantic ADMIT** or a QualityRag generation path.
- The original APX implementation may change independently. The workflow result is specific to the APX commit captured during the run.
- The normal QualityRag CI remains a transport/fail-closed check and is not native behavioral parity.

## Explicit acceptance criteria

- [x] Original APX package export contracts inspected.
- [x] Native tests exercise all three original engine entry points with nontrivial fixtures.
- [x] Workflow compiles *original* APX modules with no mock substitution.
- [x] Missing private-repo credential causes explicit failure.
- [x] Host adapter preserves `INCONCLUSIVE` even when the native algorithm reports bounded success.
- [ ] Workflow executed successfully against a specific APX SHA in a configured private-run environment.
- [ ] Results externally reviewed against APX's canonical regression corpus before claiming broad behavioral parity.
