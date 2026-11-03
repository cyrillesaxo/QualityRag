# RCT adversarial semantic drift evaluation — 30-case research corpus

**Goal:** measure *detected consequential changes*, *unresolved consequential changes*, and *false alarms on harmless controls* instead of treating every green QualityRag test as proof of semantic conservation.

This is a reproducible **small, hand-labeled synthetic evaluation**, not a medically validated question bank, an authenticated regulatory source, or an independent population-level measurement. The test sentences mention nursing, HVAC, driving, legal agreements, toy finance and everyday instructions. They are not advice, prescriptions or statements of current law.

## Dataset contract

`tools/semantic_store/data/semantic_adversarial_v1.json` has 30 immutable-by-report-hash cases:

| Domain | Consequential drift | Harmless controls |
|---|---:|---:|
| Nursing | 3 | 2 |
| HVAC | 3 | 2 |
| Driving | 3 | 2 |
| Legal | 3 | 2 |
| Finance | 3 | 2 |
| Everyday | 3 | 2 |
| **Total** | **18** | **12** |

Labels and critical distinctions are explicit. Positive cases cover negation removal, exception omission, numeric and deadline changes, and obligation weakening. Controls include harmless wording-order paraphrases and punctuation changes. Every case supplies exact source/candidate text and is identified by a stable ID. Dataset content is bound to the output by `corpus_sha256`; individual output rows use document hashes, not copied text.

## Evaluation semantics (important)

`tools/semantic_store/rct_semantic_evaluation.py` requires a detector result with the **exact original and candidate SHA-256 hashes**, `verdict` in `REFUSE/INCONCLUSIVE`, `qualityrag_admission=INCONCLUSIVE`, and `can_generate=false`. Invalid or out-of-scope results fail.

For *curated consequential changes*:
- `REFUSE` = consequential change detected.
- `INCONCLUSIVE` = **abstained / not detected**, recorded in `cases_not_detected`. This contributes a miss to the **lower-bound consequential detection rate**.

For *curated harmless controls*:
- `REFUSE` = control flagged (false alarm relative to curator label).
- `INCONCLUSIVE` = control abstention. **Never count it as a certified true negative or safe answer.**

The evaluator reports all counts, per-domain counts, individual IDs and exact source/candidate SHA-256 values. It does not return a generic accuracy number, precision, trusted true-negative rate, semantic ADMIT, or a production false-negative guarantee.

## Baseline and failure controls

The deliberately naive `TEXT_INEQUALITY_BASELINE` flags every changed byte as REFUSE. All 30 cases change wording/punctuation, so the baseline detects all 18 curated drift examples **but also falsely flags all 12 controls**. This illustrates why apparent perfect drift detection alone is not a viable semantic-conservation metric.

The tests verify both classes must be present, corpus IDs must be unique, detector source hashes must match, ADMIT and generation are rejected, every inconclusive consequential case is counted as missed, and the original native APX detector must not silently fall back to the naive comparator.

## Reproduce in ordinary CI

```bash
python tools/semantic_store/rct_semantic_evaluation.py
python -m unittest discover -s tools/semantic_store/tests \
  -p 'test_rct_semantic_evaluation.py' -v
```

This is the *baseline*, not an APX performance report.

## Real original APX execution

The private APX workflow `.github/workflows/rct-native-apx-parity.yml` now also runs:

```bash
python tools/semantic_store/rct_semantic_evaluation.py \
  --native-root /absolute/path/to/original/built/apx/packages
```

That command invokes the separately built original APX semantic-source compiler for each labeled case. If the original runtime is missing, access fails, or output violates its source-binding contract, the evaluation **fails**. It never substitutes test doubles, silently skips cases, or reports fake APX scores. A successful private run generates the inspectable **`apx-native-adversarial-metrics`** GitHub Actions artifact (14-day retention), including per-case outcomes. The artifact excludes the HMAC key, original engine source and raw text.

**The private native score is not known until this workflow has actually completed.** Inspect the artifact and recorded original APX SHA before quoting measured APX effectiveness.

## Next acceptance requirements

1. Separate curation from implementation authorship and obtain expert-adjudicated examples, including disagreement records and sources/versions.
2. Expand beyond small, English-only synthetic sentences to long authentic documents, tricky scope nesting, unit transformations, numerical context and purpose-dependent omissions.
3. Report confidence intervals and independently selected held-out samples; do not use this tiny corpus for a production error bound.
4. Evaluate both false alarms (workflow cost) and missed consequential changes (risk), broken out by semantic category and domain.
5. Measure actual sources of independent authority and deceptive witness dependencies. Do not treat cryptographic record integrity as document truth.
6. Preserve the full underlying document through tested FF-RCT reconstruction before any actual omission admission.

**No result from this harness permits semantic ADMIT or model generation.**
