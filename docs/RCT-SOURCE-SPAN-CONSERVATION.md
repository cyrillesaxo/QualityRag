# RCT source-span conservation research adapter

This additive module checks **source-anchored, explicitly supplied semantic distinctions** against a candidate document. It does not autonomously extract all semantic obligations or classify the canonical APX G1–G12 taxonomy.

## Input contract

- Exact source text and candidate text (up to 200,000 characters each).
- Exact SHA-256 digests for both texts.
- A versioned obligation inventory digest of at most 256 entries.
- Each entry has a unique ID, recognized typed distinction, required flag, exact source quote and character offsets, and optional exact candidate quote/offsets. `expected_value` and `observed_value` are typed-value **declarations from the caller**, not inferred truth.
- The input may classify actor, recipient, negation, condition, exception, deadline, number, unit, modality, scope, authority, obligation, legal effect or temporal distinctions. These are local names and **must not** be substituted for canonical APX 12G identifiers.

## Decisions

- Missing required distinction or explicitly changed typed value: `REFUSE`.
- Omitted optional distinction, unmeasured value, or matched declared values: `INCONCLUSIVE`.
- Invalid source/candidate hashes, inventory hash, quote offsets, duplicate IDs or malformed schema: reject immediately.
- **No output can ever claim `ADMIT` or `can_generate: true`.**

The checks are a finite inventory comparison, not a complete semantic proof. Even when every recorded distinction appears to match, the inventory may be incomplete or the values incorrect. A cryptographically reviewed PackSpec-to-obligation mapping is still required to establish reviewer custody, and that alone still does not prove unobserved meaning.

## Test regimes

The test corpus covers:
- Nursing exam NOT scope reversal.
- HVAC service-instruction exception omission.
- Driving permit waiting-period change.
- A legal/refund condition retained in the candidate.
- Omitted optional context, unmeasured observations, changed source and review versions, forged offsets and duplicate obligation IDs.

These are controlled synthetic sentences, not authenticated certification standards or legal authority. Cross-domain fixtures broaden falsification coverage, not claims of semantic validity.

## Reproduce

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_rct_source_span_conservation.py' -v
```

Implementation: `tools/semantic_store/rct_source_span_conservation.py`.

## Remaining integration requirements

1. Connect this obligation inventory to the canonical reviewed PackSpec compiler instead of taking a caller-provided digest as independent authority.
2. Use the original APX source-span semantic engine and actual canonical G taxonomy for semantic counterexamples, with source-version-locked fixtures.
3. Test against independently reviewed document collections and compare adjudication to expert labels; quantify missed violations and abstentions.
4. Keep every source document and omitted source segment reconstructable from its original version.
