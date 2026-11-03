# APX native semantic compatibility record — research v1

This change pins the **reported original APX stress execution**, not a semantic-completeness certificate. The versioned record is at `tools/semantic_store/data/apx_native_compatibility_v1.json`.

- Original APX Actions run: [41726055119](https://github.com/cyrillesaxo/apx/actions/runs/41726055119)
- APX revision recorded for that run: `52018f0677f53eccd75fc0951e16af5247c8f8fe`
- Stress corpus raw SHA-256: `cb01d8f9f0fc9f86e560f9f771cdae1d99be5cf01153c5a7657a69a391392ecd`
- Reported outcomes: **0/12 consequential detections**, **0/6 control flags**. All 18 original comparator results were unresolved (`INCONCLUSIVE`).
- Current combined governance schema: `rct.native-relational-semantic-governance/v0.1`. The combined signed path was previously exercised with a **mock native interface**, not with this independently verified original executable.

## Checks

Run without a scorecard to check the local immutable corpus/record relationship:

```bash
python tools/semantic_store/rct_native_compatibility.py
python -m unittest discover -s tools/semantic_store/tests -p test_rct_native_compatibility.py -v
```

If authorized to download the original APX workflow artifact, extract `qualityrag-original-apx-stress-scorecard.json` and cross-check it:

```bash
python tools/semantic_store/rct_native_compatibility.py --scorecard /path/to/qualityrag-original-apx-stress-scorecard.json
```

The optional check detects changed case IDs, source/candidate hashes, corpus hash, score and admission claims. It does not cryptographically establish who generated that scorecard; a caller could substitute another conforming JSON. For actual independent provenance, collect the workflow artifact digest, runner/commit attestations and a trusted reviewer signature.

## Adversarial interpretation

A syntactically valid scorecard with zero detections is **not** a positive semantic result. A signed role annotation can detect a reviewed inversion, but a malicious or mistaken reviewer may annotate an inverted sentence as unchanged. The next evaluation should challenge this with adversarial **annotation omissions**, swapped roles, coreference, implicit participants, compound units, negation scope, conditional dependencies, and paraphrase controls. Use independent expert adjudicators and publish both false negatives and false positives.

A future end-to-end run must execute the **original** APX engine and the signed span and role governance over identical source/candidate bytes and one pinned PackSpec IR, with a preserved, independently attested build identity. Only then can it claim native composed-path coverage. Even that would not prove semantic completeness or authorize generation.

**Hard boundaries:** `semantic_completeness=UNKNOWN`, `production_admission=NOT_AUTHORIZED`, `can_generate=false`. This is deliberately separate from production admission and from actual FF-RCT reconstruction.
