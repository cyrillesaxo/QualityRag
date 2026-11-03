# RCT typed-AST discovery experiment v0.7

Status: integrated experimental candidate compiler in APX Semantic Store branch. **Not a production semantic compiler.**

## Question tested

Can a source-grounded compiler derive a useful purpose-specific grouping without the source containing the final grouped sentence?

The typed anatomy source supplies three separate `part_of` edges, each paired with an `is_a major_region` edge. A finite grammar joins those relationships and emits a group of three members. A drawing source provides two `converges_to` edges sharing a vanishing point; a second grammar factors that common target.

Neither grouping proves the source true, semantically complete, or suitable for arbitrary downstream purposes.

## Existing integration

- `tools/semantic_store/rct_grammar.py`: validate bounded typed AST facts, discover two finite grammar patterns, compile a source-fingerprinted candidate lens with fact-level citations and cost proxies.
- `tools/semantic_store/rct_lens.py`: persist candidate using the experimental SemanticStore, retaining `INCONCLUSIVE` status; rejected if the fingerprint has been tampered with.
- `tools/semantic_store/tests/test_rct_grammar.py`: regression tests for derived anatomy groups, drawing transfer, unresolved targets, source sharing, tampering, and closure assertions.
- CI: `.github/workflows/apx-semantic-store.yml` runs Semantic Store unit tests.

## Trust and performance boundaries

- The source AST is structured input; its derivation from raw documents is not implemented here.
- `source_ref` is an unverified provenance *claim*, not authenticated custody.
- The compiler contains **two predefined grammar templates**, not open-ended grammar induction.
- A group of three observed members does not prove that no fourth member exists.
- Optional source-cited closure claims remain `UNVERIFIED_CLOSURE_ASSERTION`.
- The cost proxy reports raw counts of input facts and active group members; it is not measured runtime, full storage cost, a compression ratio, or evidence of end-to-end savings.
- The local finding `CANDIDATE_STRUCTURAL_GROUP_FOUND` must never be converted to QualityRag `ADMIT`.
- Negative evidence, source authority, semantic equivalence, PackSpec adequacy and novel-grammar validation remain outside this v0.7 compiler.

## Subsequent acceptance targets

1. Build a real document -> typed AST adapter that records source spans, ambiguities, and versioned custody.
2. Add a reviewed PackSpec contract for what the lens may omit, which questions it must support, and when it must return UNKNOWN.
3. Compare a grouped lens to original-structure and SQL materialized-view baselines using measured construction, update, storage and per-query costs across a realistic workload.
4. Propose new grammar operators through bounded synthesis, with held-out tests and independent verifier admission; do not claim algorithmic discovery from finite rule matching.
5. Add FF-RCT lenses as an optional *transformation mechanism*, with explicit historical/reconstruction payload costs and independent fidelity receipts.

Run tests from repository root:

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```
