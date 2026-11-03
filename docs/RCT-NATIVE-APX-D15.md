# Reuse canonical APX deceptive-witness D15 census in QualityRag

This integration loads the **original APX** `packages/apx-evidence/src/index.ts` implementation, specifically `buildDeception15Gate` and `deception15CellCatalog`, rather than reproducing or renaming its 15-cell taxonomy.

The canonical APX census has three families `DW`, `DD`, `DS` and five axes `DEPTH`, `BREADTH`, `CHANNEL`, `FRAME`, `IMPLICATURE`: exactly 15 combinations.

## Integration

`tools/semantic_store/rct_apx_deception_native.mjs` imports the independently built, original APX evidence engine from the trusted absolute `APX_PACKAGES_ROOT`. Missing or malformed native packages fail closed. It requires a full 15-cell check (`requireAllCells=true`) and explicitly rejects caller attempts to invent cell IDs. Each input cell carries an explicit host-declared status and named evidence references.

Output is a **QualityRag research diagnostic** with the canonical APX cells and their statuses. It never executes a real-world deception probe automatically and does not authenticate evidence-reference content or independence.

**Critical difference:** The original APX `buildDeception15Gate` may return `status=ADMITTED` or `allow_compression=true` when all supplied cell observations declare PASS. This is the original engine's *bounded local* census verdict. QualityRag MUST NEVER promote that into semantic ADMIT or FF-RCT compression authorization. The adapter always returns `qualityrag_admission=INCONCLUSIVE`, `compression_authorized=false`, `can_generate=false`, and `semantic_completeness=UNKNOWN`. Explicit failed cells produce a QualityRag `REFUSE`; other outcomes remain `INCONCLUSIVE`.

## Real original APX verification

The **Canonical APX Native Parity** workflow sparse-checks out `packages/apx-evidence` from the separately authorized original APX repository, compiles the actual original TypeScript module (without modifying the original source), then executes `test_rct_apx_deception_real.mjs`.

The tests verify original 3 × 5 catalog order, all missing cells remaining UNTESTED, failure dominance, full declared PASS not granting QualityRag admission or compression, and rejection of unknown cell IDs.

The regular open-source QualityRag CI tests syntax and absence of any substitute engine. It does **not** claim that private original-source execution has passed.

## Evidence and trust boundaries

- These synthetic tests verify correct **census API** behavior, not generation of 15 expert deceptive witnesses or independent adversarial falsification.
- A host assertion that `DW_DEPTH` passed can be false; evidence refs require independently reviewed custody, quality and authorization.
- All 15 cells declared PASS is not adequate grounds for deleting information, compressing clinical/legal source text, or granting disclosure.
- The automatic private APX workflow requires an authorized read-only GitHub repository secret `APX_REPO_READ_TOKEN`; until a successful run is verified, native algorithm execution remains unconfirmed.
- This work does not claim native FF-RCT, full cross-domain semantics, or production admission.

Run transport checks locally:

```bash
node --test tools/semantic_store/tests/test_rct_apx_deception_transport.mjs
```

For true native checks, first build the original `apx-evidence` package and run:

```bash
APX_PACKAGES_ROOT=/absolute/original/apx/packages \
  node --test tools/semantic_store/tests/test_rct_apx_deception_real.mjs
```
