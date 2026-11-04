# Semantic Codex v1.1 — typed relation candidates and explicit review costs

This extends the existing four-regime research harness (`docs/SEMANTIC-CODEX-FOUR-REGIMES-V1.md`) with a **bounded, caller-supplied relation extraction/review ledger**. It does **not** extract relationships automatically, implement all 12G grammar operators, authenticate human reviewers, verify meaning or sign PackSpec verdicts.

The experimental `K/B/C/T` field is a **role tag**, not a complete operational encoding of the APX typed semantic grammar.

## Inputs

The first JSON file is the existing `qualityrag.four-regime-input/v1.0` manifest. The second is a separate `qualityrag.relation-review-input/v1.1` ledger.

For the `event` → `decision` relation and `decision` → `minutes` witness in the v1.0 example, use:

```json
{
  "schema": "qualityrag.relation-review-input/v1.1",
  "human_review_authentication": "UNVERIFIED",
  "candidate_relations": [
    {
      "from": "event",
      "to": "decision",
      "relation": "RELATES_TO",
      "role": "K",
      "quoted_evidence": "Cyrille discussed the contract",
      "evidence_source": "event",
      "review_verdict": "SUPPORTED",
      "extraction_ms": 7.0,
      "review_ms": 11.0
    }
  ],
  "witness_reviews": [
    {
      "target": "decision",
      "source": "minutes",
      "review_verdict": "UNCERTAIN",
      "review_ms": 5.0
    }
  ]
}
```

The quote must be an exact substring of a source text in the manifest. That proves **string presence only**, not that the quoted statement supports the relation. An absent quote is reported as a failed source anchor, not hidden. The ledger must enumerate **exactly** the declared graph relation and witness inventories: omitted review work cannot silently be treated as free or complete. Verdicts are `SUPPORTED`, `REJECTED`, or `UNCERTAIN` and remain unauthenticated assertions.

## Run

```sh
PYTHONPATH=tools/semantic_store python tools/semantic_store/run_relation_review.py \
  --manifest regime-example.json \
  --ledger review-ledger.json \
  --repetitions 5 \
  --output /tmp/relation-review-v11.json
```

The receipt contains the four-regime experiment results and an additional cost/review section: extraction milliseconds, relationship-review milliseconds, witness-review milliseconds, rejected and uncertain counts, role distribution, source quote anchor failures, and reproducible manifest hashes.

**Cost attribution limitation:** These durations are **caller-supplied**, not measured by a clock in the reviewing app and not audited. They cannot establish a real labor cost or end-to-end savings. The current four-regime graph uses the declared candidate edges even if a reviewer marks one rejected; it is an **experimental replay**, not a reviewed production graph. It never returns `ADMIT`, authenticated witnesses or a verified false-positive rate.

## Tests

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_relation_review_experiment.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

The next production-relevant experiment needs a real extraction executor that records processing time, independently reviewed labels with authenticated provenance, rejection-aware graph construction, relation-level adversarial witnesses and matched baselines. Those are not part of this milestone.
