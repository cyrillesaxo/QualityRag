# Real file ingestion lab — synthetic content

This lab generates **actual PDF, DOCX and HTML files**. The PDFs deliberately include many irrelevant pages and a governing clause deep in an annex to simulate retrieval over long documents. All policy content is invented. It does **not** contain scanned-page OCR, authentic company documents, embeddings or a full RAG service.

## Run

```bash
python -m pip install -r examples/enterprise-rag/requirements.txt
python examples/enterprise-rag/build_documents.py
PYTHONPATH=sdk/python python examples/enterprise-rag/ingest_documents.py
```

The generator creates an 80-page handbook, 188-page annex, DOCX runbook and HTML incident report in the ignored `generated/` directory. Parsing uses `pypdf`, `python-docx` and `HTMLParser`; ranking uses simple lexical overlap.

Expected result: generic search finds the operational text but not the governing EU control, and QualityRag reports `INCONCLUSIVE`. A targeted search can locate page 187 of the annex. This is a deterministic educational example, not a measured model accuracy improvement.

**Safety boundary:** The fixture's evidence mappings are authored, not autonomously verified. For real documents, authority, timestamps, scope, exception precedence and source independence must be validated separately. QualityRag v0.1 only enforces obligations explicitly included in its PackSpec.

## Attribution

Conceptual research lineage: **Cyrille Eloundou**, [APX](https://apx.guide/) and its PackSpec / semantic governance principles.
