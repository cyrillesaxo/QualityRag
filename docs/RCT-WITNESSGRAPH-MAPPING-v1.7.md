# RCT v1.7 — WitnessGraph obligation mapping

This experimental adapter reuses **the actual Python SDK WitnessGraph** in `sdk/python/qualityrag/compiler.py`, not a newly authored witness evaluator.

## Purpose

A governed RCT lens cannot infer that a protected distinction is independently supported merely from a structural AST witness. An obligation map therefore assigns a distinct existing evidence requirement to every declared required or optionally omitted predicate.

The bridge calls the canonical `compile_pack` and `evaluate_compiled` functions to collect:

- source-count findings scoped to each requirement;
- origin-label dependency groups and witness IDs;
- `wgap` missing-source counts and contradiction diagnostics;
- scope, authority, time-validity and evidence metadata diagnostics.

**The observed origin field is a caller-supplied label. Distinct labels do not prove independent origins or authenticated provenance.** Therefore a metadata `ADMIT` never promotes the RCT lens beyond `INCONCLUSIVE`. A canonical metadata contradiction maps to an explicit RCT `REFUSE`.

## Fail-closed contract

The binding is immutable by source/lens/pack fingerprints and insists that every required and optional distinction has exactly one *distinct* declared obligation. This is an experimental restriction rather than a claim that real PackSpecs naturally map one-to-one. Unmapped distinctions, missing PackSpec requirements, duplicate obligation reuse, changed source content, changed mappings and invalid source scope fail locally.

Even if all declared obligations are metadata-satisfied, the following are **unresolved**:

- external source custody and reviewer authority;
- whether the PackSpec obligations cover the full intended purpose;
- whether the mapped evidence is semantically relevant to each distinction;
- whether a proposed omission is genuinely safe;
- the general information reconstruction/fidelity requirements from FF-RCT.

The bridge does not execute probes, HCR, RCOC, WBC, nor independently verify WitnessGraph source dependency beyond the canonical SDK's origin-label grouping. Those mechanisms must be integrated through their real implementations and authenticated receipts.

## Reproduce

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

Implementation: `tools/semantic_store/rct_witness_bridge.py`  
Tests: `tools/semantic_store/tests/test_rct_witness_bridge.py`  
Earlier canonical ConstraintIR bridge: `tools/semantic_store/rct_packspec_bridge.py`

The two adapters intentionally retain distinct policy contexts: the existing unified gate evaluates reviewed ConstraintIR while this adapter exposes the existing Python SDK's WitnessGraph/coverage diagnostics. Neither is the other's semantic authority, and neither creates a permission to generate from an RCT candidate.

## Next acceptance milestone

1. Require the *same* reviewed source PackSpec to govern both typed ConstraintIR and the witness obligation policy, with a cryptographically verifiable mapping receipt.
2. Prove independent witness lineage rather than merely distinct declared origin strings.
3. Map permitted omissions to explicit semantics and challenge them with adversarial witnesses/unknown-unknown probes.
4. Attach actual FF-RCT reconstruction and mutability evidence, evaluate total execution cost against SQL baselines.
