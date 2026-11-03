# RCT v1.2 — branching, supervised grammar induction

**Scope:** bounded typed-AST grammar *candidate* research. Not a general autonomous grammar inventor, trustworthy PackSpec interpreter, or semantic admission engine.

## What changed

v1.1 induced a sequential path `P1 → P2 → P3`. v1.2 introduces a different **operator topology**: parallel conjunction over a shared subject/object pair.

```text
Positive: X --evidence_a--> Y  AND  X --evidence_b--> Y
Negative: X --evidence_a--> Y  WITHOUT evidence_b
Negative: X --evidence_b--> Y  WITHOUT evidence_a
```

The search uses the set of predicates shared by all **explicitly positive examples**, enumerates bounded 2-element combinations, and checks **all explicitly labeled positive and negative pairs**. A unique consistent pair becomes a proposed `CONJUNCT_PARALLEL_EDGES` grammar. Multiple consistent pairs yield `UNKNOWN/AMBIGUOUS_BRANCH_RULE`. Exhaustion of the allowed enumeration yields `UNKNOWN/SEARCH_BUDGET_EXCEEDED`.

The abstract conjunction combinator was authored in advance; its predicate names are selected by data, not invented from first principles.

## Evidence and completeness

- Negative labels are supplied externally and require a source reference; their reliability is unverified.
- Missing edges in a finite supplied graph do not establish real-world absence. Only *explicitly labeled* pairs are scored.
- Positive witnesses carry source fact IDs. Failing held-out negatives become explicit counterexamples.
- The candidate fingerprint is checked again at evaluation and before lens compilation. The assessment binds the same held-out source fingerprint.
- All lenses persist as `INCONCLUSIVE` through the existing Semantic Store; no test-level `SAT` implies QualityRag admission.
- PackSpec completeness, independent provenance, meaning conservation, and FF-RCT transformation costs remain unresolved.

## Reproduction

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

Code: `tools/semantic_store/rct_branch_induction.py`  
Tests: `tools/semantic_store/tests/test_rct_branch_induction.py`

## Next research acceptance criteria

1. A typed **operator grammar**, not just separate templates, supporting composition (`PATH`), conjunction (`AND`), projection (`PROJECT`), and guarded abstraction (`ABSTRACT`) with bounded cost.
2. Train/test splits by **problem family and structure**, not solely renamed nodes with identical edge arrangements.
3. An authorized PackSpec that defines which contradictions, missing facts, and omitted distinctions block particular lens operations.
4. Compare the discovered operator to a proper relational SQL conjunction/join baseline, and include proof, update, and FF-RCT costs.
5. Only elevate a proposed grammar to trusted use through an independent verifier integrated with the canonical QualityRag gate.

This experiment deliberately does not promise a new mathematics result or universal semantic compression.
