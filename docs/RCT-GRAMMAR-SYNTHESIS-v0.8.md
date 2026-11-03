# RCT grammar synthesis experiment v0.8

**Status: research candidate, not production semantic authority.**

This experiment advances the APX Semantic Store from two explicitly programmed domain groupings to **data-mined relation composition proposals** over a typed AST.

## What is discovered

Given recurring paths

```
X --projects_to--> Y --belongs_to--> Z
```

the compiler mines the pair of predicate labels from the source data and proposes a reusable derived operator

```
X --derived:<fingerprint>--> Z
```

The two-hop composition **operator family is programmed**. The relation pair is selected from observed paths. This is bounded grammar induction, not the invention of a previously unknown mathematical algorithm. Its semantics are structural paths only.

## Governance

- The training source and independent validation source are version-fingerprinted.
- Finite-graph structural equivalence is checked by independently enumerating reachable two-hop results for each validation subject.
- Every derived edge retains source-fact IDs. Source authenticity remains UNVERIFIED.
- Budget exhaustion emits UNKNOWN rather than a positive proof.
- Validation only establishes equivalence **for the supplied finite graph and operator interpretation**; it cannot establish domain truth, completeness, valid semantic composition, applicability outside the two-hop regime, or correctness of arbitrary source information.
- All candidate persistence through `rct_lens.persist_lens` remains `INCONCLUSIVE`.
- No external PackSpec approval, FF-RCT reconstruction, canonical WBC minimization, HCR probing or production trust is claimed.

## Research limit

The current cost proxy counts derived pairs but omits measured compilation, memory, maintenance, database query, or FF-RCT reconstruction costs. Do not compare its timing with SQL yet.

## Next acceptance test

1. Use a reviewed PackSpec to declare exactly which question family a proposed derived relation may answer and which information may be omitted.
2. Measure total cost of deriving and maintaining the relation versus both SQL recursive execution and SQL materialized views.
3. Split examples by **structure and domain**, not just renamed node labels; otherwise 'held-out' transfer remains weak evidence.
4. Evolve the operator template search to typed AST rule synthesis, with formal/independent proof when available.
5. Integrate canonical FF-RCT for multiscale transformation, with governed fidelity and actual decoding cost.

Run `python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v`.
