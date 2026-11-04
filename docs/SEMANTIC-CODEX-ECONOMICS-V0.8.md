# Semantic Codex v0.8 — FF-RCT information lifecycle economics

This is a **bounded scenario calculator** using a measured v0.7 paired experiment receipt. It does **not** demonstrate an actual economic advantage. It records gaps and refuses to treat unavailable costs as zero.

## Research question

For a fixed corpus and workload, when does paying to create an additional semantic representation become economically preferable to simpler retrieval?

The relevant lifecycle components are:

`C(total) = indexing + changed-source reindexing + queries + verification + retained storage + model loading + external services + energy + review`.

The current calculator covers the first five terms **only if the caller explicitly supplies the missing inputs**. Model loading, energy, review, and external service costs remain unmeasured, so even a calculated crossover is **not a production total-cost claim**.

## Input: actual v0.7 paired receipt

First generate a v0.7 receipt as described in `docs/SEMANTIC-CODEX-PAIRED-BENCHMARK-V0.7.md`. That receipt contains one-run observed indexing and query timings for two arms:

1. Filename keyword lookup — deliberately weak text-only baseline.
2. Existing Semantic Codex visual search — an additional model index and cosine ranking.

**The arms do not provide equivalent capabilities**. Faster or cheaper filenames alone are not a substitute for image understanding; no semantic parity is asserted. The model's initialization time is excluded from the v0.7 timing.

## Scenario JSON

Create `scenario.json` with explicit *assumed* or independently measured numbers:

```json
{
  "repetitions_per_query": 100,
  "changed_sources": 2,
  "baseline_update_ms_per_source": 3.0,
  "visual_update_ms_per_source": 125.0,
  "baseline_storage_bytes": 30000,
  "visual_storage_bytes": 250000,
  "baseline_verification_ms": 15.0,
  "visual_verification_ms": 90.0,
  "price_per_cpu_second": 0.001,
  "price_per_byte_month": 0.00000000002,
  "retention_months": 6.0
}
```

**Numbers above are arbitrary illustration inputs, not measurements or recommended prices.**

```sh
PYTHONPATH=tools/semantic_store python tools/semantic_store/run_economics.py \
    --receipt /path/to/paired-benchmark.json \
    --scenario scenario.json \
    --output /tmp/economics-v08.json
```

To run an **incomplete** scenario that avoids guessing, provide only `repetitions_per_query` and `changed_sources`. The output retains one-run observed timings, models repeat query time, but returns `total_lifecycle_cost: UNKNOWN` and no crossover.

## Method / interpretation

- **Observed:** initial directory indexing, extra visual indexing and one measured query per benchmark prompt, from the original receipt.
- **Modeled:** N identical repetitions of each prompt using one-run query times. This is **not actual repeated-query measurement**; does not include runtime drift, caches, initialization or background load.
- **Supplied:** source-change reindexing time, review/verification time, retained storage bytes and prices. These can be assumptions unless supported by external receipts.
- **Break-even condition:** only computed if all supplied components are present and observed average visual query time is lower than the filename baseline. It is the mathematical crossover for the supplied scenario, not a guarantee, a statistically validated break-even point, or an endorsement of the unequal-capability baseline.
- **No crossover:** if visual query time is not lower, `query_executions_required` is `null`. If inputs are missing, no total-currency or break-even claim is reported.
- **Quality:** finite precision/recall can be read from the v0.7 receipt; they are not collapsed into cost. FF-RCT comparison requires accuracy thresholds and matching information obligations before a cost-optimal strategy could be claimed.
- **Governance:** input provenance, dataset fingerprint, source constraints and `INCONCLUSIVE` admission remain explicit. No user identity recognition or PackSpec verification.

## Next experiment

Build a **true repeated-workload runner** to measure cold/warm query latency distribution, repeated updates and actual disk bytes with matched end-to-end service costs. Compare against equal-capability modern image-caption/vector search baselines and independently labeled multi-regime content. Only then can we distinguish an actual amortized advantage from a theoretical crossover.

## Tests

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_economics.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```
