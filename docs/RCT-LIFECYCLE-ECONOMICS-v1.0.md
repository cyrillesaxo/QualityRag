# RCT Lifecycle Economics and Transfer v1.0

This experiment extends v0.9 to test **information-creation cost, repeated query work, one source mutation, full reconstruction cost, and a second query phase**. The candidate is a *bounded structural grammar operator*, not an autonomously invented mathematical operation.

## Reproduction

From the QualityRag repository root:

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
PYTHONPATH=tools/semantic_store python - <<'PY'
import json
from rct_lifecycle import run_cross_topology_suite
experiment = run_cross_topology_suite(trials=3, repetitions=8)
for topology, data in experiment["topologies"].items():
    print(topology, json.dumps({
      "identical_answers": data["identical_answers"],
      "mutation_changed_answers": data["mutation_changed_answers"],
      "median_ns": data["median_ns"],
      "comparative_verdict": data["comparative_verdict"],
      "qualityrag_admission": data["qualityrag_admission"]
    }, indent=2))
PY
```

## Compared lifecycle

For each backend:
1. Load original structured source and indexes.
2. Build the backend's precomputed structure if applicable.
3. Answer the identical finite two-hop relation workload.
4. Insert one new fact that changes the query results.
5. Fully rebuild the precomputed structures.
6. Re-answer the same workload and verify identical results.

The three backends are **direct indexed SQL joins**, **SQL materialized and indexed view**, and the **Python candidate-lens materialization**. Source ingestion/loading and update insertions are shared costs included in each total. Structural candidate discovery and finite evaluation are included in the candidate-lens build.

The measured comparison is against the minimum total time of **both SQL baselines**; reporting a speedup relative to only direct SQL is prohibited.

## Transfer

A single grammar operator mined from chain-shaped training data is applied to:
- another chain-shaped graph;
- a branch-and-fan-out graph containing multiple destinations and distracting relationships.

This is a genuine *topology* change, but still has the same operator family and named predicate pair. It does not demonstrate new type discovery or natural-language understanding.

## Governance and open work

- Source references are claims, not authenticated provenance.
- An experimental workload contract restricts purpose and operations but is **not an approved or complete PackSpec**.
- No automatic permission to omit a required semantic distinction is granted.
- Every candidate is `INCONCLUSIVE` for QualityRag admission even if finite structural equality is SAT.
- SQL incremental view maintenance, training dataset preparation, parser compilation, data-size memory, disk and FF-RCT reconstruction costs are **not included**.
- Results are interpreter/hardware dependent and cannot establish broad product performance superiority.

The next acceptance target is an authenticated PackSpec gate for admissible lenses and comparable fully measured operators. A separate milestone must introduce **typed grammar synthesis that can produce operator forms not predetermined by the template**, independently verify them and test cross-workload transfer.
