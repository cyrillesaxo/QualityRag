# RCT purpose-scoped semantic lens v1.5

**Research-only.** This module attaches a purpose declaration and a local omission contract to a verified typed-AST rule candidate. It is not a PackSpec parser, an authenticated review process, or a production QualityRag admission gate.

## Boundary and lens semantics

Creation-time input consists of:
- version-fingerprinted structured source and explicitly labeled query examples;
- a typed-AST candidate trained on a separate source and evaluated against this source;
- a caller-declared purpose, required predicate distinctions and optional predicate distinctions.

The compiler protects:
1. every source fact bearing a required predicate;
2. every source fact appearing in a positive proof witness in the assessment.

It excludes from the **active lens only** facts with explicitly permitted optional predicates that are not protected. It re-evaluates the source AST on the contracted structure and requires the answers to all labeled structural queries to remain unchanged. The original source is referenced by its hash and has not been deleted or semantically certified.

Example: A classification relation is derived by `AND(PATH(p,q),r)`; context-only edges can be omitted for this query family without changing the declared five example answers. No claim is made that those edges are safe to omit for other purposes.

## Fail-closed behavior

- Missing or conflicting required/optional declarations -> rejected.
- Changed source content or changed labels -> rejected by fingerprints.
- Tampered purpose contract, rule or evaluation -> rejected.
- Changed answers for any declared example -> rejected.
- Source authenticity, completeness of the declared obligations, independent witnesses and domain-level semantic preservation remain UNKNOWN.
- All outputs and Semantic Store admission receipts remain **INCONCLUSIVE**.

## Reproduce

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

Code: `tools/semantic_store/rct_purpose_lens.py`  
Tests: `tools/semantic_store/tests/test_rct_purpose_lens.py`

## Remaining acceptance gates

- Parse **reviewed and authenticated PackSpec** obligations using the canonical QualityRag compiler and gate, not a parallel parser.
- Require source-level witness authority and dependent-origin checks through the canonical WitnessGraph/HCR/RCOC implementations.
- Model unknown-unknown risk: a passing finite set of labeled examples does not prove that every semantically critical distinction survived.
- Introduce FF-RCT multiscale views as the underlying source/reconstruction mechanism and account for their actual construction/update costs.
- Run held-out examples from different real domains and compare work with strong SQL/materialized-view baselines.
- Only a trusted external verifier may promote a candidate beyond INCONCLUSIVE.
