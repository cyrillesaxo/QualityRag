# Quickstart: first evidence decision

Clone [QualityRag](https://github.com/cyrillesaxo/QualityRag) and follow your [language-specific guide](README.md).

QualityRag gates **caller-provided evidence metadata** against PackSpec requirements, before the application authorizes a generated answer.

## Minimal policy

```json
{"id":"eligibility-demo","version":"1","requirements":[{"id":"rule","min_independent_sources":2,"max_age_seconds":3600}]}
```

## Evidence

```json
[
 {"id":"w1","requirement_id":"rule","origin":"A","source_ref":"doc:A#1","status":"SUPPORTS","observed_at":"2026-11-02T10:00:00Z"},
 {"id":"w2","requirement_id":"rule","origin":"A","source_ref":"doc:A#2","status":"SUPPORTS","observed_at":"2026-11-02T10:00:00Z"}
]
```

Evaluate at a **fixed clock** of `2026-11-02T10:05:00Z`. Both records share origin A, so the result is `INCONCLUSIVE`, independent source count is 1, and the finding includes `INSUFFICIENT_INDEPENDENT_EVIDENCE`. Change w2's declared origin to B, and the metadata gate yields `ADMIT` if no other blocking evidence exists. That does **not** establish that A and B truly are independent.

For runnable examples, see `examples/python_demo.py` and `examples/hidden-exception/demo.py`.

## Integrate safely

1. Define a server-owned, versioned PackSpec.
2. Retrieve documents with access control and construct validated, provenance-aware witness metadata.
3. Evaluate **before** calling your model; on `REFUSE` or `INCONCLUSIVE`, do not invoke the answer generator.
4. Return an appropriate clarification/refusal with bounded reasons; protect receipts from sensitive content.
5. Reevaluate when policy, time horizon or sources change.

The base gate checks counts, timestamps and contradictions. Only the extended compiler checks declared scope and authority labels and emits Wgap. See [concepts](concepts.md).
