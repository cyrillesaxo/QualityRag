# Semantic Codex v1.2 — source-anchored explicit relation extraction

This milestone replaces a portion of manually keyed relationship candidates with an **executable deterministic syntax extractor**.

A source can contain declarations such as:

```text
Cyrille discussed the contract.
RELATE event RELATES_TO decision
```

On a full line, `RELATE <known_source_id> <UPPERCASE_RELATION> <known_target_id>` is converted to a structural candidate with exact **line and start/end character offsets**, source text hash, quotation and stable candidate ID. The referenced source IDs must exist within the finite authorized inventory. Malformed declarations are reported, not silently accepted.

This is intentionally **not** extraction of arbitrary relationships from natural language. For example, the sentence “Cyrille discussed the contract” does not by itself establish a `RELATES_TO` edge to a different file.

## Candidate creation

Use the finite source format from `docs/SEMANTIC-CODEX-FOUR-REGIMES-V1.md`, adding explicit `RELATE` lines to the relevant source text. Example:

```json
{
  "schema": "qualityrag.four-regime-input/v1.0",
  "sources": [
    {"id":"event","text":"Cyrille discussed the contract.\nRELATE event RELATES_TO decision\n"},
    {"id":"decision","text":"A provisional decision was recorded"},
    {"id":"minutes","text":"Minutes are provisional"}
  ],
  "relations": [{"from":"event","to":"decision","relation":"RELATES_TO"}],
  "witnesses":[],
  "questions":[{"id":"q1","term":"Cyrille","relation":"RELATES_TO",
                "expected_targets":["decision"],"required_witnesses":[]}]
}
```

Generate candidates:

```sh
PYTHONPATH=tools/semantic_store python tools/semantic_store/run_explicit_relation_extraction.py \
  --manifest manifest.json --output /tmp/candidates-v12.json
```

The candidate output is **not** an authorization to create graph links.

## Review-gated graph projection

In Python, call `project_reviewed_relations(store, extraction, sources=..., verdicts=..., principal=..., authorize_source=...)` with one `candidate_id`/verdict pair for each candidate. Allowed verdicts: `SUPPORTED`, `REJECTED`, `UNCERTAIN`.

The graph already needs to contain the immutable, correctly source-versioned `BENCHMARK_CANDIDATE` nodes from the existing four-regime test setup. Only reviewer-**SUPPORTED** candidates may produce a graph edge; rejected and uncertain candidates do not. Even a supported edge explicitly carries `review: CALLER_SUPPORTED_UNAUTHENTICATED` and `verification: NOT_PERFORMED`. The projection refuses incomplete reviews, altered candidate inventories, invalid source declarations, missing candidate nodes and source access denials. Repeated identical projections are idempotent.

## Verification

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_explicit_relation_extraction.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

The tests cover real character spans, invalid and unknown references, non-projection of rejected/uncertain candidates, idempotency, pre-read authorization, inventory tampering and immutable-source expectations.

## Important boundaries

- This is a **small deterministic grammar**, not the full 12G grammar; no NLP, LLM extraction, directionality inference, contradiction checking, WBC, HCR, RCOC or trusted PackSpec admission occurs.
- The source declaration is text supplied by the dataset author; its factual correctness and the reviewer's identity remain unverified.
- The extractor measures only its own deterministic processing duration. Review time, model costs, semantic correctness and total lifecycle savings remain unmeasured.
- Production review should enforce authenticated reviewer roles, a source-verified evidence span policy, evidence independence, model-specific error budgets, and a PackSpec fail-closed evaluation before making downstream claims.

The next milestone can compare this explicit grammar with an independently evaluated natural-language relation extraction model on an identical, pre-labeled corpus, including spurious relation prevention, rejection cost and source-preserving behavior.
