# Typed role-binding grammar (experimental) — source-anchored semantic relations

## Why this exists

The original APX source comparator returned `INCONCLUSIVE` on **all 12** intentionally difficult consequential changes in the native [role-binding stress run](https://github.com/cyrillesaxo/apx/actions/runs/41726055119). This is a real falsification of any claim that checking a multiset of lexical atoms establishes preserved meaning. See `docs/RCT-NATIVE-ROLE-BINDING-STRESS.md` for exact source revisions and results.

A relation like `PAY(OBLIGOR=Alice, BENEFICIARY=Bob)` is different from `PAY(OBLIGOR=Bob, BENEFICIARY=Alice)`, even when every surface token is present in both sentences.

## New grammar

`tools/semantic_store/rct_role_grammar.py` accepts **explicit source/candidate typed role annotations**, where a fact contains:
- A stable fact ID and typed predicate;
- One or more role → canonical entity/typed-value bindings;
- An exact quoted source/candidate substring and integer offset for every binding.

The grammar compares canonical predicate+role identity, **not order of words**, so reviewed passive voice reformulations can retain the same annotations, while a reviewed actor/beneficiary inversion triggers `ROLE_BINDING_CHANGED`.

Source/candidate document SHA-256, source/candidate role-inventory digests and exact quote anchors must match. Missing required source facts and changed predicates/roles cause **REFUSE**. New candidate facts that lack a corresponding source fact are explicitly **ADDED_FACT_UNREVIEWED** and remain unresolved. Exact matches remain **INCONCLUSIVE** rather than ADMIT.

The finite runtime is bounded by 200 KB per text, 128 facts per side and 24 bindings per fact.

This is not a general NLP extractor: **the reviewer is responsible for semantic identity and role annotations**. A malicious or mistaken reviewer can assign the wrong actor ID to a matching quote; the exact quote check cannot detect that semantic lie.

## Signed review

`tools/semantic_store/rct_signed_role_grammar.py` reuses the canonical QualityRag `signed_bundles` Ed25519 policy and observation attestation verifier, with a separately authorized reviewer key and a durable replay nonce.

The signed review binds:
- Original and candidate source bytes' SHA-256;
- Both exact typed role inventories;
- The evaluated audit fingerprint;
- The governing reviewed PackSpec ConstraintIR digest, source digest, and all node IDs;
- Review scope `EXACT_REVIEWED_ROLE_GRAPH_CLAIMS_ONLY`.

The verifier reconstructs the role graph from supplied bytes **before** consuming the review nonce. It refuses altered or replayed signed documents, inconsistent inventories and untrusted reviewers.

**Cryptographic review authenticates approved annotations, not the truth or exhaustive completeness of the underlying semantic roles.** The output remains `semantic_completeness=UNKNOWN`, `semantic_truth=NOT_INDEPENDENTLY_ESTABLISHED`, `qualityrag_admission=INCONCLUSIVE`, `can_generate=false`.

## Regression regimes

- Actor/recipient/beneficiary reversal;
- Left/right laterality change;
- Unit change with unchanged numeric value;
- Before/after ordering reversal;
- Passive voice with unchanged reviewed roles;
- Missing and newly introduced source facts;
- Forged quoted offsets and stale inventory digests;
- Duplicate role IDs and fact IDs;
- Actual Ed25519 tamper, unsigned completeness claim, policy substitution and replay.

Run:

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_rct_role_grammar.py' -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_rct_signed_role_grammar.py' -v
```

## Integration and unresolved acceptance

This is a **typed relational preservation layer**, not a replacement for canonical APX 12G, KBCT, WitnessGraph, HCR, WBC or RCOC. Binding those layers requires a reviewed cross-ontology mapping; do not fabricate `G` coordinates or claim inferred `K,b,c,t` meaning.

Next, construct a real inference/extraction path for source role assertions and independently judge it on evidence-bearing documents, with explicit reviewer corrections, false-negative accounting and purpose-specific PackSpec obligations. Strong autonomous extraction cannot be inferred from these synthetic tests. Native FF-RCT reconstruction and independent publisher provenance remain outstanding.

No output grants compression, disclosure, or generation authority.
