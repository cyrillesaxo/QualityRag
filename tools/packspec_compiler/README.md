# PackSpec Source Compiler v0.1 — Evidence-aware inspection, not semantic execution

A conservative compiler for rich **APX PackSpec sources** (YAML, JSON, text-bearing PDF), developed for QualityRag.

**Author and research lineage:** Cyrille Eloundou, [APX](https://apx.guide/). The source compiler is an experimental QualityRag implementation, not an assertion that the full APX grammar has been compiled.

## What it actually does

1. Reads a bounded local YAML, JSON, or PDF source (2 MB; PDFs up to 200 pages).
2. Preserves the SHA-256 of the original *source bytes*, source ID/version when structured, and cited source locations (JSON pointer or PDF extraction page/line). For candidate text, records a quotation hash.
3. Detects **candidate** clauses using explicit structure and lexical cues. All candidates are `REVIEW_REQUIRED`; **zero** are auto-admitted as enforceable.
4. Optionally generates a reviewer worksheet; all mappings start `approved:false`.
5. With an explicit, source-hash-pinned and reviewer-authored mapping, outputs a **QualityRag v0.1 evidence-presence projection**. It never converts a semantic predicate into a proven rule.

This compiler is intentionally **not** a language model, HCR investigator, reliable PDF OCR engine, or production policy signer. PDF tables and diagrams may be omitted or misordered. Line numbers depend on the extraction library. Source file authentication and reviewer identity are not implemented.

## Run against your original PackSpecs

From the repository root:

```bash
python -m pip install -r tools/packspec_compiler/requirements.txt

python tools/packspec_compiler/compiler.py \
  /path/to/packspec-semloan-v0.4.0.yaml \
  --out /tmp/semloan.inspection.json \
  --draft-mapping-out /tmp/semloan.review.json

python tools/packspec_compiler/compiler.py \
  /path/to/question-fan.json \
  --out /tmp/question-fan.inspection.json

python tools/packspec_compiler/compiler.py \
  /path/to/FFI_packspec_v0_6_0.pdf \
  --out /tmp/ffi.inspection.json

python tools/packspec_compiler/compiler.py \
  /path/to/sel_packspec.pdf \
  --out /tmp/software-selling.inspection.json
```

For image-only PDFs, this utility **fails closed** with an OCR-required error. Never silently treat missing extracted text as evidence that no constraints exist.

## Review and compile a narrow projection

First inspect the report and original source. In the generated review worksheet:

- **Delete** candidates that are irrelevant, duplicate, or not applicable.
- Choose clear `requirement_id` values only for evidence-presence obligations the existing evaluator can check.
- Supply `reviewed_by` (a record label, **not** authenticated identity), a substantive `rationale`, and `approved: true` for every retained item.
- Keep the `source_sha256` unchanged. A modified source invalidates the approval.
- Never reinterpret `ADMIT` as proof of semantic truth, correctness, domain completion, or policy authorization.

Example worksheet entry (the `candidate_id` must come from the actual inspection report):

```json
{
  "schema": "qualityrag.manual-mapping/v1",
  "source_sha256": "<paste source.sha256 from inspection JSON>",
  "policy_id": "reviewed-learning-evidence",
  "policy_version": "1.0",
  "rules": [
    {
      "candidate_id": "C0001",
      "requirement_id": "cold-retrieval-evidence",
      "min_independent_sources": 1,
      "reviewed_by": "domain-owner",
      "approved": true,
      "rationale": "Require a source-attested cold retrieval result, but do not treat its presence as mastery certification"
    }
  ]
}
```

Run:

```bash
python tools/packspec_compiler/compiler.py /path/to/source.yaml \
  --out /tmp/source.report.json \
  --mapping /tmp/approved.mapping.json \
  --policy-out /tmp/approved.evidence-policy.json
```

The report includes mapping receipts linking each projected requirement back to an extracted source location and quotation fingerprint. The resulting standalone policy can be loaded using [internal, property, external file, or Studio sources](../../docs/PACKSPEC-SOURCES.md).

## Contract boundary

| Capability | v0.1 |
| --- | --- |
| Parse bounded YAML and JSON source | Implemented |
| Extract text-bearing PDF page text | Implemented |
| Preserve source and quotation hashes | Implemented |
| Detect candidate clauses | Heuristic; **not complete** |
| Emit review-required inventory | Implemented |
| Enforce approval before emitting evidence projection | Implemented (declared approval flag, unauthenticated) |
| Enforce full SEMLOAN, Question Fan, FFI, FFI Teacher, sales semantics | **Not implemented** |
| Automated authority, provenance, independence, applicability | **Not implemented** |
| OCR or diagram understanding | **Not implemented** |
| Signed canonical policy bundles or reviewer authentication | **Not implemented** |

## Tests

```bash
python -m unittest discover -s tools/packspec_compiler/tests -p 'test_*.py'
```

Unit tests use synthetic YAML, JSON, and **actual generated multi-page PDFs**, plus approval, source-drift, duplicate, invalid, and OCR-absence negative cases.

**Next bounded milestone:** reviewed semantic IR, typed predicates, executable probes, and independent field validation. This is not a simple rename of source text into a JSON `requirements` array.

## Typed ConstraintIR (experimental)

The [typed IR extension](TYPED-IR.md) records reviewed EVIDENCE_PRESENCE, TEMPORAL, AUTHORITY, PROBE and PREDICATE nodes with source hashes and reviewer mappings. Only EVIDENCE_PRESENCE can project to the existing QualityRag v0.1 metadata gate. The other four are explicitly deferred; no semantic evaluator or probe runner is implied.
