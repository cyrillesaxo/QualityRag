# Semantic compiler — first implementation slice

`qualityrag.compiler` (Python) and `compiler.ts` (TypeScript) implement a **bounded prototype**, not full semantic inference.

It compiles requirements to typed obligations (scope, required authority label, evidence count, freshness). A witness graph groups repeated claims by declared origin. Wgap reports missing independent origins or explicit failure reasons. REFUSE dominates INCONCLUSIVE; only fully covered declared obligations ADMIT.

**Security boundaries:** Authority and origin are caller-provided labels and not independently authenticated. Distinct labels do not prove independence. A witness contradicting outside the declared scope is not treated as a governing contradiction. Neither engine invokes an LLM or crawls source material. Use a trusted upstream evidence collector.

Java's existing v0.1 gate remains unchanged pending parity implementation. Do not treat the two-language compiler prototype as cross-language equivalent until a Java implementation and shared conformance fixtures pass.

## Next
- Shared JSON Schema for the extended contract
- Java implementation and cross-language golden fixture vectors
- G1–G12 and D15 independently reviewed APX parity
- HCR/W_min and model-routing cost instrumentation
