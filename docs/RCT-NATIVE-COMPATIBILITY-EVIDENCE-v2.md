# Corrected original APX native stress run — compatibility evidence v2

This version records the successful **original compiled APX comparator** from [Actions run 41731710651](https://github.com/cyrillesaxo/apx/actions/runs/41731710651), executed at APX revision `ce5a65671a17b373281e3ee4d187d1e5d481e414` (PR #128 head). APX merged the exporter fix as `9a4f8a3e4a3fe77d576369217525e54d0162b8b0`. The artifact archive id is `13277955469`, archive SHA-256 `818bbd1753ee958f027005f01c5b9e8a04b7e0a9ab0d58a1ffa3aa80d295d3ec`.

Both JSON files inside the downloaded original artifact successfully passed strict parsing; the SHA-256 of its ZIP matched GitHub's reported digest. The original native curated scorecard reports 18/18 consequential detections and 0/12 control flags; the harder 18-case role-binding scorecard reports **0/12 consequential detections and 0/6 control flags**. These are separate synthetic datasets, not population accuracy estimates.

## Reproduce checks

```bash
python tools/semantic_store/rct_native_compatibility_v2.py
python -m unittest discover -s tools/semantic_store/tests -p test_rct_native_compatibility_v2.py -v
```

To verify the original (not rewritten) stress scorecard extracted from artifact 13277955469, run:

```bash
python tools/semantic_store/rct_native_compatibility_v2.py --scorecard /path/to/qualityrag-original-apx-stress-scorecard.json
```

Without `--scorecard`, the verifier checks manifest/corpus consistency but **does not** establish per-case agreement with the actual artifact. The unit test's scorecard fixture is constructed for adversarial verifier coverage and **does not** constitute an actual native run. Merely supplying conforming JSON is not independent producer attestation. Independently bind the ZIP digest and GitHub run provenance before using the supplied file as evidence.

## Distinct evidence versions

- v1 remains anchored to native run 41726055119, whose stress scorecard was malformed by a literal trailing backslash-n.
- v2 records the corrected native exporter from run 41731710651 without overwriting or silently normalizing v1.

**Unchanged epistemic boundary:** native comparator execution is not signed-role end-to-end execution; typed-role annotations are manually reviewed, not independently evaluated automatic extraction; semantic completeness is `UNKNOWN`; production admission and content generation remain unauthorized. A separately attested combined replay, external gold labels, source custody, and FF-RCT reconstruction testing remain required.
