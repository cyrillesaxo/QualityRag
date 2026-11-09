# JEPA × RCT: falsifiable paired experiment (v0.1)

**Status:** research harness, not an implemented JEPA model or a demonstrated hybrid. Owner: QualityRag/APX research. Research lineage: Cyrille Eloundou.

## Question

Can a genuinely trained JEPA-style predictive representation improve task-relative cost/accuracy when paired with existing RCT/PackSpec governance, *without increasing decision-critical omissions*?

**Do not substitute** the repository's CompressAI `neural_baseline.py` for JEPA. CompressAI is an image compression baseline, not a JEPA world model.

## Existing integration boundaries

- `tools/semantic_store/rct_benchmark.py`: structured two-hop graph workload, not semantic admission.
- `tools/semantic_store/rct_packspec_bridge.py`: preserves canonical REFUSE; all non-refusals remain INCONCLUSIVE until independently verified omission sufficiency.
- `tools/packspec_compiler/unified_gate.py`: canonical gate. Do not create a second gate or upgrade these comparison checks to ADMIT.
- `FR.MD`: research invariants and story acceptance states.

## Reproduce the *harness* (not a trained-model benchmark)

```bash
python -m unittest tools.research.test_jepa_rct_compare -v
python -m tools.research.jepa_rct_compare tools/research/synthetic_manifest.json
```

The fixture intentionally reports **UNAVAILABLE** for both JEPA and RCT: neither has been executed for this paired dataset. This is correct, not a failed model benchmark.

## Required experimental protocol

1. Freeze independent source corpus, tasks, regime labels, purpose and reviewed PackSpec. Include held-out boundary cases: negation, inequalities, payer/payee swaps, rare exceptions, contradictory witnesses, unknown evidence, distribution shift.
2. Train or load an authentic, identified JEPA-family checkpoint with licensed immutable weights, hash, code/version, architecture, hardware, seed and split manifests. No network or arbitrary code execution in the benchmark path. Record which JEPA variant and whether it uses action-conditioned dynamics.
3. Implement task decoding from JEPA embeddings *without secretly supplying the gold answers*; record its predictions and genuine cost measurements. Run RCT under the identical task contract. A hybrid must be its **own third separately measured arm**, not conflated with RCT.
4. Have a separate reviewer annotate gold fields and PackSpec source anchors. Measure required distinction accuracy, refusal behavior, performance on unseen regime boundaries, source-to-answer provenance, reproducibility, p50/p95 latency, total storage, checkpoint distribution, training/compile amortization, inference energy where measured.
5. Feed actual predictions into the machine-readable manifest and run the comparator; keep failures. The comparator only checks **finite exact fields** and never asserts semantic equivalence.
6. Only after PackSpec/ConstraintIR mapping, independent WitnessGraph verification and authorized signatures may a separate governance process consider semantic admission; this script cannot certify it.

## Hypotheses and falsification

- H1: JEPA predicts nuisance-invariant structure better than an equivalently budgeted input-space baseline on held-out data.
- H2: RCT explicit typed obligations reduce harmful omission rates relative to unconstrained task decoding.
- H3: A combined system achieves better measured total cost at *matched preservation quality*. Reject H3 if boundaries fail, omitted exceptions increase, or model/activation overhead erases benefits.
- H4: Predictive-error spikes identify useful boundary candidates; reject if out-of-regime recall/precision does not exceed a prespecified trivial detector.

**Report:** all arms, exact preprocessing, selection bias, held-out split, confidence intervals, missing records and negative results. Never claim novelty or superiority solely from synthetic fields or a model name.

## Manifest structure

See `synthetic_manifest.json`. Each task has `id`, `regime`, `gold` (reviewed exact fields), and `required`. Each candidate has `status: MEASURED`, `artifact_sha256`, `model_or_grammar_version`, `run_ref`, and a `responses` object keyed by task IDs. The harness checks fields, marks missing runs unavailable, and always returns `qualityrag_admission: INCONCLUSIVE`.

## Next implementation gates

- Actual JEPA checkpoint adapter with pinned offline reproducibility.
- Paired evaluation fixture derived from independently reviewed real source documents.
- Separate hybrid arm and measurement schema covering lifecycle costs.
- A reviewed PackSpec-to-obligation mapping in the canonical gate.
