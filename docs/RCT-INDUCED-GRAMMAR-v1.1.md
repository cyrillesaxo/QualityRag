# RCT Induced Grammar v1.1 — experimental

The source representation is a bounded typed AST graph. A source-bound learner receives **explicitly labeled positive and negative pairs**, searches paths of length 1–4, finds a unique shortest predicate sequence that agrees with every label, and tests that proposal on a different held-out graph.

This is more flexible than the fixed two-hop candidate mechanism in v0.8: the operator sequence and depth are selected from observed relations and supervision. **The compositional-path search family remains predefined.** This is bounded rule induction, not evidence of independent mathematical invention or unbounded semantic understanding.

## Run

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

Implementation: `tools/semantic_store/rct_induction.py`.
Tests: `tools/semantic_store/tests/test_rct_induction.py`.

## Evidence contracts

- Every labeled pair carries an unverified `source_ref`.
- Training **requires positive and negative labels**; unlabeled pairs remain epistemically unknown.
- The shortest grammar is chosen only if it is **unique** and consistent with all labels.
- Insufficient search depth, ambiguous minimal rules, and budget exhaustion return `UNKNOWN`.
- Evaluation uses a different source and explicitly checks negatives as well as positives.
- Negative witnesses that a generated rule predicts as positive produce `COUNTEREXAMPLE` and finite-graph `UNSAT`.
- All matched positives carry fact-ID paths, not unsupported prose explanations.
- Rule and assessment fingerprints are checked again before compiling a lens; changing a rule after verification is rejected.
- All persisted candidates remain `QualityRag INCONCLUSIVE` through the existing Semantic Store adapter.
- `SAT` applies **only** to the explicitly labeled pairs in the supplied finite graph and does not authorize a domain-level claim.

## Outstanding research requirements

1. Replace user-authored labels with independently sourced, governed witness records; require authenticated PackSpec source selection and evidence admission.
2. Test structural diversity beyond renamed graph labels, including branching paths and adversarial false positives.
3. Support genuine grammar operators beyond a fixed relation-path combinator family, with a typed generator and verifier.
4. Compare full compilation, proof, update, storage and FF-RCT reconstruction costs against optimized SQL and other baselines.
5. Use FF-RCT as a multiscale structural lens and history substrate, while treating scope and admitted meaning as a PackSpec/QualityRag responsibility.

Candidate structural verification is necessary but never sufficient for production trust.
