# Evidence-coverage evaluation — measured *within synthetic fixtures*

The evaluation uses real generated **PDF, DOCX, and HTML bytes** from `build_documents.py` and extracts their text. It runs three queries through a simple lexical ranker, maps retrieved document/page IDs to **human-authored obligation labels**, and calls the existing QualityRag Python evaluator.

## Reproduce

```bash
python -m pip install -r examples/enterprise-rag/requirements.txt
python examples/enterprise-rag/build_documents.py
PYTHONPATH=sdk/python:examples/enterprise-rag python examples/enterprise-rag/evaluate_coverage.py
PYTHONPATH=sdk/python:examples/enterprise-rag python -m unittest discover -s examples/enterprise-rag -p 'test_*.py'
```

## Measurements

| Measure | Definition | Important limitation |
| :--- | :--- | :--- |
| Labeled obligation recall | Fraction of query-required labels represented by top-k retrieved document/page IDs | Labels are synthetic and curated by the author |
| Baseline answers with missing requirements | Queries with at least one retrieval hit while the complete PackSpec is not covered | **Proxy**: no conventional LLM is run; not hallucination rate |
| QualityRag admissions with missing requirements | Number of `ADMIT` decisions despite absent declared obligations | Evaluates deterministic gate only |
| Appropriate abstentions | `INCONCLUSIVE` results when declared obligations were missing | Doesn't show whether a human would find those obligations relevant |

**Interpretation:** A non-zero baseline proxy and zero unsafe gate admissions in these fixtures shows that an explicit evidence gate can block an answer when the same retriever supplies incomplete policy coverage. It does **not** demonstrate improvement against a well-configured, production-grade RAG baseline, real unstructured corpora, OCR output, or human-verified document truth.

The policy and evaluation labels are pre-authored. No automatic exception discovery or relevance classification is provided. A stronger comparison must use a fixed external document collection, hybrid search, blind labels, controlled prompts, actual LLM generations and confidence intervals.

Research lineage: **Cyrille Eloundou** and [APX](https://apx.guide/) semantic governance / PackSpec concepts.
