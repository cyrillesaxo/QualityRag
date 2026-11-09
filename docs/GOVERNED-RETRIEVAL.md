# Governed retrieval orchestration (reference)

The `GovernedRetrievalPipeline` wires a tenant-scoped retrieval index to a mandatory PackSpec evaluation callback. It withholds generation on REFUSE, INCONCLUSIVE, unknown, or cross-tenant verdicts. An explicit tenant-bound ADMIT is required before calling an optional generator. Citations are derived from retrieved chunk coordinates, not from model output.

**Important:** The callback is an integration seam, not yet a wired QualityRAG SDK evaluator. Callers must use the actual versioned PackSpec evaluator; a callback that always returns ADMIT defeats the safety boundary. Even a valid ADMIT only certifies declared metadata requirements, not truth or factual entailment of generated prose. Citation presence does not establish claim-level attribution. No production endpoint, persistent index, Drive extraction, vector search, retrieval freshness guarantee or end-to-end evaluation is claimed.
