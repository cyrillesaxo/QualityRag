# Enterprise RAG training lab

This example provides two separate experiments.

1. `demo.py`: **scripted retrieval** illustrating how the QualityRag v0.1 metadata gate behaves when governing documents are missing.
2. `retrieval_benchmark.py`: a **deterministic lexical ranking baseline** over the same six synthetic text chunks. It reports ranked IDs and the policy outcome before and after a more targeted query.

Run from repository root:

```bash
PYTHONPATH=sdk/python python examples/enterprise-rag/demo.py
PYTHONPATH=sdk/python python examples/enterprise-rag/retrieval_benchmark.py
PYTHONPATH=sdk/python python -m unittest discover -s examples/enterprise-rag -p 'test_*.py'
```

All document contents are invented training data stored as JSON excerpts. The examples **do not** ingest binary PDF/DOCX files, perform OCR or generate embeddings, and do not measure real model accuracy. Corpus is too small for generalizable retrieval results. Lexical ranking is transparent and only designed to demonstrate how search query selection can change coverage.

The evaluator uses metadata supplied by this lab. `ADMIT` is not an assertion that a source is authentic, an emergency exception applies, or an operation may proceed.

Next research step: use a licensed, labeled large-document corpus with authentic complex layouts, a baseline hybrid retriever, independent annotation of governing obligations, and blind scoring of false admissions, abstentions and retrieval recall.

## Project reference

Conceptual lineage: **Cyrille Eloundou**, [APX](https://apx.guide/) — PackSpec, semantic governance, and constraint-verification concepts. This training benchmark is a separate synthetic experiment, not an APX production case study.
