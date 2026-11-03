# RCT v1.3 — compositional typed operator grammar

**Experimental:** The goal is a common typed grammar that combines operator families; it is not a production information-quality verifier.

## Typed syntax

```text
Relation ::= EDGE(predicate)
           | PATH(Relation, Relation)
           | AND(Relation, Relation)
```

- `EDGE` denotes the finite set of source/target pairs with that predicate.
- `PATH` composes two relations at a shared intermediate object.
- `AND` intersects their source/target pairs, retaining a witness from each branch.
- The generator currently searches `EDGE`, two-edge `PATH`, two-edge `AND` and `AND(PATH(EDGE, EDGE), EDGE)`. The evaluator handles recursively nested typed ASTs, but the generator **does not explore all nested AST shapes**.
- The chosen AST minimizes a simple AST node-count proxy within the bounded generated family, with **UNKNOWN** for ties, no candidates or search exhaustion.

## Distinguishing research fixture

For a positively labeled pair `(X,Y)`, the source contains:

```text
X --p--> M --q--> Y
X --r------------> Y
```

One negative contains only the `p;q` path; another contains only `r`. A single path or single predicate is insufficient. The generated candidate `AND(PATH(EDGE(p),EDGE(q)),EDGE(r))` agrees with the labeled examples, while a new contradictory edge in held-out data becomes an explicit counterexample.

## Trust boundary

- Source and labels are finite, synthetic, externally authored records. References are unauthenticated.
- Missing edges are described as absent **in the supplied graph**, not false in the world.
- Labeled negatives are not inferred from an open-world lack of evidence.
- Structural SAT means agreement with labeled pairs on this graph only.
- Every produced lens remains `INCONCLUSIVE` when persisted using `rct_lens.persist_lens`.
- Verified source authority, PackSpec sufficiency, WBC minimization, WitnessGraph dependence, FF-RCT reconstruction and real performance costs remain unimplemented.
- No invention of a new mathematical operator is claimed: the operator syntax and search shape were authored in advance.

## Run

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

Code: `tools/semantic_store/rct_operator_ast.py`  
Tests: `tools/semantic_store/tests/test_rct_operator_ast.py`

## Next acceptance criteria

1. Add a declarative, type-checked operator grammar search allowing composition, guarded abstraction and projection under explicit resource limits.
2. Make the actual source-grounded PackSpec decide which labeled obligations the lens may satisfy, and when omissions block admission.
3. Replace synthetic held-out examples with independent source and witness datasets in at least three unrelated regimes.
4. Compare measurable, complete lifecycle costs against the equivalent relational algebra query and precomputed SQL view.
5. Integrate FF-RCT's actual scale/history/reconstruction primitives instead of an illustrative graph adapter.
