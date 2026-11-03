# RCT Typed Grammar Generator v1.4

This experimental extension replaces a fixed list of AST shapes with a **declarative, typed, bounded relation-operator grammar**. The grammar supplies predicate signatures, allowed constructors and resource limits; the generator enumerates type-compatible ASTs under a maximum node count. It does **not** invent new mathematical constructors.

## Syntax and type rules

```text
Relation<A,B> ::= EDGE<P:A→B>
                | PATH(Relation<A,M>, Relation<M,B>)
                | AND(Relation<A,B>, Relation<A,B>)
```

`PATH` is allowed only when the left target type equals the right source type. `AND` requires equal endpoint types. Commutative conjunctions are de-duplicated canonically. Types are **externally declared, unauthenticated hypotheses**; the compiler does not prove that source facts or their ontology conform to them.

## Search and governance

- No dynamic code evaluation; grammar input only permits EDGE, PATH, AND and bounded typed signatures.
- Candidate AST size is bounded; grammar definitions and source fingerprints are recorded.
- Explicit positive and negative labels are required.
- A candidate is returned only if **exactly one** minimum AST node-count expression matches all labeled examples; ambiguity, insufficient candidates and budget exhaustion yield `UNKNOWN`.
- Held-out validation independently checks the chosen AST against labeled pairs, emitting positive fact-ID paths and negative counterexamples.
- Source refs and predicate meanings are unverified.
- QualityRag admission remains **INCONCLUSIVE** even for a finite labeled-graph `SAT`.
- The existing `rct_lens.persist_lens` adapter stores the candidate and the evaluation receipt in the experimental Semantic Store.

## Reproduce

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

Module: `tools/semantic_store/rct_typed_grammar.py`  
Tests: `tools/semantic_store/tests/test_rct_typed_grammar.py`

## Known limitations

- The grammar compiler evaluates only graph relations with two endpoints; grammar production does not yet support guarded abstraction, projection, quantification, unknown-aware negation, or cross-modal FF-RCT structure.
- The enumerator is deliberately bounded and can exhaust its budget before finding a candidate.
- Its node-count minimum is not evidence of minimal processing work, and no speed advantage is claimed.
- Held-out examples are synthetic and may share generative structure with training examples.
- There is no authenticated PackSpec, WBC minimization, WitnessGraph independence enforcement, RCOC/HCR attestation, or verified FF-RCT reconstruction.

Next: use a reviewed PackSpec to define admissible purpose-specific transformations, and test a more diverse held-out dataset with independently authenticated witnesses.
