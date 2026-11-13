# Reversible semantic completeness: source-accounting increment

**Experimental.** This is a deterministic lossless byte-accounting substrate; it does **not** establish semantic completeness or authorize conclusions.

`UniversePackSpec` records source size/digest; `PackSpecProjection` stores admitted source byte spans; `DiffPackSpec` stores every remaining byte and an UNKNOWN semantic verdict.

## Contract

- `Decode(Merge(P, DiffP, U)) == original_source` (byte-exact).
- Every source byte is accounted for exactly once.
- Hash and source identity must match.
- Byte reconstruction never promotes `semantic_completeness` above UNKNOWN.

Run: `python -m unittest discover -s tests -p 'test_reversible_completeness.py'`.

## Integration (next increment)

Use existing PackSpec compiler typed-IR nodes as semantic projections. Keep source spans, WBC admitted/adapted/residual/rejected receipts, and independent anti-witness tests. Define the obligation universe explicitly. Only a separate governance gate may issue a scoped semantic completeness certificate. A full residual reproducing the source is NOT semantic success.

This module is not wired to production, Studio, APIs, or the existing evidence gate. It intentionally avoids changing runtime behavior.
