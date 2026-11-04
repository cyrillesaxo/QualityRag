# Semantic Codex v1.0 — four representation regimes, same evidence questions

This experiment contrasts four information-processing regimes against the **same finite questions**, using the existing SemanticStore, Codex JSON adapter, typed KnowledgeGraph traversal, WitnessGraph edges and bounded query_context API.

It tests whether additional structure makes particular **candidate operations** possible. It does **not** claim R3/R4 are proven better, that candidate graph edges represent authentic facts, or that PackSpec requirements have been independently evaluated.

| Regime | Method | Can establish |
| --- | --- | --- |
| R1: Raw text | Case-insensitive scan of original text fields | Mentions of the search term; no source relations |
| R2: Codex lexical | Indexed scalar text matching | The same text seed references with source version anchors |
| R3: Typed relation | R2 seeds plus authorized KnowledgeGraph relation traversal | Candidate relation targets, not verified implications |
| R4: Evidence requirements | R3 candidates plus source-linked WitnessGraph presence checks | Whether a required, finite witness inventory is present in a bounded traversal; never source truth or ADMIT |

R3 and R4 intentionally have additional expressive power. Their timings are **not** an equivalent-capability contest: the cost of building reviewed relations/witnesses or of validating source authenticity is not included. R4 **never releases an admitted result**, even when all expected witness nodes are present; it returns INCONCLUSIVE pending a trusted verifier. Missing required witnesses produce `REFUSE_MISSING_WITNESS_PRESENCE`.

## Run a concrete example

Save the following as `regime-example.json`:

```json
{
  "schema": "qualityrag.four-regime-input/v1.0",
  "sources": [
    {"id": "event", "text": "Cyrille discussed the contract"},
    {"id": "decision", "text": "The provisional decision was recorded"},
    {"id": "minutes", "text": "Meeting minutes reference the provisional decision"}
  ],
  "relations": [
    {"from": "event", "to": "decision", "relation": "RELATES_TO"}
  ],
  "witnesses": [
    {"target": "decision", "source": "minutes"}
  ],
  "questions": [
    {"id": "complete", "term": "Cyrille", "relation": "RELATES_TO",
     "expected_targets": ["decision"], "required_witnesses": ["minutes"]},
    {"id": "missing", "term": "Cyrille", "relation": "RELATES_TO",
     "expected_targets": ["decision"], "required_witnesses": ["event"]}
  ]
}
```

```sh
PYTHONPATH=tools/semantic_store \
python tools/semantic_store/run_four_regime_experiment.py \
  --manifest regime-example.json --repetitions 5 --output /tmp/regime-results-v1.json
```

The runner builds a disposable SQLite index with version-bound source hashes. It measures graph ingestion phases, finite query runtimes, SQLite file bytes, and labels the difference between **text mention**, **typed candidate relation**, and **witness-presence check**. The `expected_targets` are reviewer-supplied and unauthenticated; candidate recall is finite-set candidate recall only.

There are no source PDFs or real video inputs in this fixture. This is a **small structural causal-isolation test** for regime operators, not the final multimodal comparison. Review labels, graph edges and witnesses are declared in the manifest; their creation and human review time are **not** measured. R1 reads already loaded text fields, whereas R2–R4 query SQLite; their I/O and indexing costs are not equalized. The report explicitly marks semantic-equivalence, source authenticity and full lifecycle cost as **NOT ESTABLISHED**.

## Next controlled study

Use independently reviewed real multimodal evidence and a **capability-matched** baseline that can answer the same relationships and evidence obligations. Measure human annotation, ingestion, source revisions, representation changes, updates, multi-query latencies, preservation of required distinctions, and verified output coverage. Introduce regime-specific requirements before evaluating costs; expensive representations that preserve no additional required information should be rejected.

## Tests

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_four_regime_experiment.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```
