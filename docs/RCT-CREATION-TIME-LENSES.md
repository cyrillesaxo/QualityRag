# RCT creation-time lenses — experimental v0.6

This module is an *adaptor to the existing APX Semantic Store PR #33*, not a second semantic database. It creates **candidate** lenses at information-creation time. It cannot establish source truth, the completeness of a PackSpec, or a novel grammar.

## Executable integration

```python
from rct_lens import compile_lens, persist_lens

source = "The human body has three main parts: head, trunk, and limbs."
lens = compile_lens(
    source, lens_id="elementary-body", purpose="identify-major-regions",
    required=("head", "trunk", "limbs"),
    permitted_omissions=("heart-location",),
)
# Existing SemanticStore from store.py, initialized with SQLite.
record = persist_lens(store, lens=lens,
                      source_id="anatomy-reference",
                      revision="source-v1",
                      packspec_digest="EXTERNAL_PACKSPEC_DIGEST")
assert record["admission"] == "INCONCLUSIVE"
```

## Semantic invariants

- Source character spans, quotations and fingerprints are retained as **claims**, not authenticated facts.
- A missing distinction is UNKNOWN, never an assertion that the source contradicts it.
- A locally satisfied structural inventory does not establish PackSpec completeness.
- Every persisted lens and admission receipt is immutable under the current prototype schema.
- Multiple lenses can share a source revision, but a source revision cannot be reused with a different source fingerprint.
- Candidate receipt admission is INCONCLUSIVE; no adapter must turn this into ADMIT.
- A lens's permitted omissions are only declarations; they have not been established safe by the current compiler.
- Rule patterns are narrow demonstrations for anatomy and drawing; broad language, negation, polysemy, and provenance authority require separate vetted engines.

## Next research steps

1. Extend the creation compiler from literal patterns to **typed source AST distinctions**, with explicit citation and ambiguity handling.
2. Compile a **lens scope** and loss contract from a reviewed PackSpec. Route actual execution to QualityRag's authenticated unified gate; leave unavailable checks INCONCLUSIVE.
3. Provide alternative grammar candidates and a measurable processing cost; compare against source-grounded baselines on unseen tasks.
4. Treat FF-RCT as a **versioned transformation/reconstruction provider**, not as a source of truth or completeness authority. Preserve its encoding, history, decoding and accounting receipts separately from semantic verdicts.
5. Connect canonical APX WBC, HCR and RCOC receipts, with their verified scope, rather than reimplementing their algorithms.
6. Run held-out experiments on anatomy, drawing and one unrelated domain; measure construction cost, active work, maintenance, permitted omissions and false admissions.

Run: `python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v`.
