# Private RAG retrieval foundation

`apps/registry/src/private-retrieval.js` provides source-preserving chunking, lexical scoring, provenance, revision replacement, source deletion and strict Balafons tenant boundaries. It is an **in-memory reference implementation**, not a production index, vector database, embeddings pipeline, semantic reranker or LLM answer generator. Search results are **candidate evidence**, never an ADMIT verdict.

Production completion requires: durable per-tenant index; Drive document content extraction and incremental synchronization; ingestion worker consuming the transactional inbox; PackSpec evaluation and evidence sufficiency before generation; citations and refusal behavior; source ACL refresh and deletion propagation; performance/recall evaluation; end-to-end OAuth and adversarial multi-user tests. Keep the PackSpec gate authoritative and fail closed when the index is incomplete.
