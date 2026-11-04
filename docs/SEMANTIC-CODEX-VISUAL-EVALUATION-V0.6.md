# Semantic Codex v0.6 — measurable visual retrieval and candidate provenance graph

This milestone adds **two experimental mechanisms**, both built on the v0.5 visual scene retrieval pipeline. No claim of production semantic accuracy, person recognition, universal coverage or verified truth is made.

## 1. Finite labeled benchmark

`visual_evaluation.evaluate_visual_results` computes **precision@k** and **recall@k** only for an explicitly labeled *complete, bounded, authorized* v0.5 result set.

The caller must supply one independently reviewed `RELEVANT`, `NOT_RELEVANT`, or `UNCERTAIN` label for every returned source/revision/record. All source and record identities must match exactly. Incomplete candidate inventories, duplicate labels and truncated results refuse evaluation instead of reporting misleading recall. Uncertain labels return `INCONCLUSIVE_UNCERTAIN_LABELS`, with no numeric score.

```python
from visual_evaluation import evaluate_visual_results

search_result = find_visual_scenes(
    store, "person giving a presentation", namespace="local",
    principal=principal, authorize_source=authorization,
    encoder=encoder, max_hits=100)
# Labels must be obtained through an INDEPENDENT review process, not generated
# from search score or assumed from the filename.
labels = [
    {"source_id":hit["source_id"], "revision":hit["revision"],
     "record_id":hit["record_id"], "label":"UNCERTAIN"}
    for hit in search_result["results"]
]
receipt = evaluate_visual_results(search_result, labels=labels, k=5)
# This initial all-uncertain example intentionally yields INCONCLUSIVE.
```

A complete result set *within the indexed pool* does not prove that the directory has been fully processed, that all media frames were sampled, or that the model generalizes to other data. Reference labels are not signed; a production benchmark must separately establish reviewer independence and provenance. `precision_at_k` and `recall_at_k` refer only to the labeled finite scope; with no relevant labels, recall is **undefined** (`null`). This is not a person identification evaluation.

## 2. Graph projection for candidate derivations

`visual_graph.project_visual_candidates` maps model-ranked results into **`MODEL_RETRIEVAL_CANDIDATE` nodes** in the existing immutable Semantic Store, each linked through a `WITNESS` edge to its existing, version-bound `CODEX_RECORD`.

This means that the graph can answer:

> Why did the retrieval engine rank this frame?

The answer is a model candidate derived from a particular indexed source record, with model identity, prompt digest, source revision, timestamp anchor and similarity score.

The edge relation is `DERIVED_FROM_CODEX_RECORD`, with `independent: false`, `verification: NOT_PERFORMED`. **It is not independent corroboration, a verified fact, evidence of person identity or a PackSpec-pass decision.**

The projection refuses inaccessible source records, nonexistent source versions, unexpected result types and candidate counts over 30. It performs all writes atomically and is idempotent for identical results. To explore the graph, use existing `query_context` with an explicit **per-object** authorization policy: neither source-level ACL nor a candidate's existence grants permission to other graph objects.

## Reproducible validation

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_visual_evaluation_graph.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

The tests use **real generated image pixels**, deterministic synthetic visual/text encoders, source revision checks, unauthorized private media and adversarial malformed receipts. They prove software control-flow/metric calculation and provenance storage, **not** OpenCLIP retrieval quality. A future evidence-backed benchmark needs a real curated corpus with multiple photographers, varied scenes and labeled videos, plus measured recall@k/precision@k by regime, frame coverage, latency and total extraction cost.

## Next

Expose evaluation and provenance on the Studio interface only after a reviewed label collection protocol and secure object-level ACLs are available. Then compare lexical-only, image hash and OpenCLIP retrieval on the *same* held-out dataset, with FF-RCT lenses for cost-vs-information preservation instead of assuming a better representation necessarily performs better.
