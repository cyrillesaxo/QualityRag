# Semantic Codex v1.3 — bounded linguistic relation extraction and contradiction quarantine

This milestone introduces a **working but deliberately narrow English-language relation candidate extractor**. The earlier v1.2 extractor recognizes only explicit `RELATE` declarations. This version can recognize certain ordinary English sentences such as:

```text
event supports decision.
event does not support decision.
decision references minutes.
```

Both positive and negative statements are preserved with exact source-text character spans and source hashes. The first two statements trigger a **potential syntactic contradiction** on `(event, SUPPORTS, decision)`. The conflict is not a proof that either statement is false; versions, context and timing may differ. All conflicting candidates are quarantined from graph projection.

## Recognized patterns

The source and target must be **literal known IDs** from an authorized manifest (not arbitrary names or pronouns). Supported third-person singular positive verbs: `supports`, `references`, `relates to`, `depends on`. Supported negative forms: `does not support`, `does not reference`, `does not relate to`, `does not depend on`. Source IDs must be declared in the same manifest. Unrecognized entity references and grammatical forms are recorded as unresolved, not interpreted through guesswork.

The extractor processes bounded source text lines, retaining a source ID, source SHA-256, excerpt, exact character offsets, line number, polarity and a stable candidate fingerprint. It cannot understand implicit relationships, pronouns, modalities (may/might), temporal scope, exceptions, conditional statements, negation scope beyond the listed forms, or source authenticity. It does not make person-identity assertions.

## Run comparison against v1.2

Provide the v1.0 source-manifest shape (see `docs/SEMANTIC-CODEX-FOUR-REGIMES-V1.md`) containing the listed English phrases, optionally alongside `RELATE` declarations:

```sh
PYTHONPATH=tools/semantic_store python tools/semantic_store/run_linguistic_relations.py \
  --manifest /path/to/manifest.json \
  --output /tmp/linguistic-v13.json
```

The receipt compares **actual extraction runs**: explicit declaration candidate count, linguistic candidate count, typed positive relation keys, potential contradiction inventory and extraction time. It does **not** claim a false-positive rate, recall, total review cost or grammatical equivalence because no independent ground truth is authenticated.

## Optional review-gated graph projection

Python callers can use `project_linguistic_reviews(store, extraction, sources=..., verdicts=..., principal=..., authorize_source=...)`. Every candidate must have a unique verdict and a caller-supplied finite `review_ms`. Only positive, unconflicted, reviewer-`SUPPORTED` candidates may write an edge to the existing versioned `BENCHMARK_CANDIDATE` nodes. Even those edges remain `CALLER_SUPPORTED_UNAUTHENTICATED` with `semantic_verification: NOT_PERFORMED`. Both sides of any potential polarity contradiction are excluded, regardless of reviewer endorsement.

Projection re-extracts from the full authorized source inventory and checks candidate fingerprints before writing transactionally. Unsupported, rejected, uncertain, conflicting, tampered or unregistered candidates never become graph edges.

## Validation

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_linguistic_relation_extraction.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

Tests cover exact spans, grammatical restrictions, unknown entities, source access, explicit-vs-English extraction, positive/negative collisions, rejection/uncertainty, reviewer completeness, tampering, idempotent projection and immutable source-version linkage.

## Research boundary and next steps

This release is **not a general NLP relation extractor, LLM semantic verifier, authenticated PackSpec evaluation, WBC/RCOC execution or complete 12G typed grammar**. Measuring extraction duration does not measure independent reviewer effort. The next comparative experiment needs a held-out dataset with independent relationship/polarity ground truth and a mature NLP/LLM baseline, scored for false candidates, missed candidates, contradiction accuracy, human review time, and provenance preservation at equivalent semantic obligations.
