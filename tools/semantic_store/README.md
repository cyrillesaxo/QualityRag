# APX Semantic Store — experimental prototype

**Status:** candidate persistence and graph-read prototype. NOT an authoritative semantic database, production ACL, source-authenticity checker, or replacement for APX engines.

See [the canonical APX concept registry](../../docs/APX-SEMANTIC-STORE-REGISTRY.md).

## End-to-end research delivery

The integrated **experimental** workflow (typed grammar -> purpose lens -> all-pairs finite conservation -> reversible reference reconstruction -> independently signed reviewed obligations -> signed provenance and custody -> fail-closed QualityRag diagnostic) is documented at [RCT end-to-end research delivery](../../docs/RCT-END-TO-END-RESEARCH-DELIVERY.md).

Run the synthetic single-command walkthrough with `python tools/semantic_store/rct_demo.py`. The strict signed path is `rct_end_to_end.attach_reviewed_signed_governance`; no candidate can generate an answer or become semantically ADMIT based on these checks. To use actual APX WBC/HCR/RCOC algorithms, the optional `rct_apx_native.mjs` adapter loads their independently built original private workspace packages and fails closed otherwise.

The reversible `rct_reference_frame.py` codec is **not native FF-RCT**. The bounded structural proof does **not** establish universal semantic sufficiency or trusted publisher authority.

## Implemented

- `store.py`: immutable source revisions; semantic versions; typed KnowledgeGraph, WitnessGraph and regime edges; non-authoritative admission receipts; native APX receipt storage. SQLite triggers reject UPDATE/DELETE while the schema is controlled by this API.
- `knowledge_ir.py`: validates the existing reviewed `qualityrag.constraint-ir/v1` source mapping, preserves all obligations and emits `qualityrag.knowledge-ir/v0.1` candidates. `persist_constraint_ir` atomically records them in the semantic store.
- `apx_receipts.py`: validates the outer v0.1 HCR and RCOC receipt envelopes and stores them without treating `BOUNDED_DIAGNOSIS` or `BOUNDED_DIFF` as full policy admission.
- `query.py`: deterministic bounded graph retrieval, caller-supplied per-object authorization, and explicit `INCONCLUSIVE` status.
- `tests/`: fingerprints, immutability, rollback, tampering, unknowns, access-control filtering, query bound, HCR/RCOC receipt behavior.

## Run tests

```bash
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
python -m compileall -q tools/semantic_store
```

Runs in GitHub Actions via `.github/workflows/apx-semantic-store.yml`.

## Input boundary

Existing QualityRag compiler emits reviewed ConstraintIR. The new KnowledgeIR bridge only materializes reviewed *candidate* nodes. It never generates trusted facts from arbitrary prose, never runs untrusted predicates, and never represents deferred or evaluable checks as executed. Source digests only establish a claimed fingerprint and do not authenticate a source.

### Minimal example

```python
import sqlite3
from tools.semantic_store.store import SemanticStore
# Existing compiler returns reviewed ConstraintIR:
# from tools.semantic_store.knowledge_ir import persist_constraint_ir
db = sqlite3.connect(":memory:")
store = SemanticStore(db)
store.initialize()
# persist_constraint_ir(store, source_id="manual", revision="v1", ir=reviewed_ir)
```

The modules currently use sibling imports (`from store import ...`) and are invoked from their tool directory or its test harness. The snippet illustrates the model only, not an independently packaged Python import path.

## APX integrations intentionally NOT implemented

- Source-meaning extraction, correct canonical G1–G12 assignment, and a source-to-knowledge grammar compiler.
- Full WitnessGraph provenance verification, dependent-origin adjudication and D15 deceptive-witness investigations.
- Verified WBC/W_min minimization or protected-verdict equivalence proof.
- Executing HCR, RCOC, RCT, FFI-RCT or FF-RCT from the store; this prototype only imports the HCR/RCOC outer result envelopes.
- TERM dependency replay, KBCT and cost-aware probing, question-fan orchestration, PackSpec v1 semantic admission, and verified agent feedback.
- Production Postgres migrations, row-level security, signed evaluator receipts and external source attestation.

**Security:** SQLite is suitable for an isolated prototype only. Do not expose `store.db` or raw `object_version` as a web endpoint. `query_context` requires an authenticated principal and application-provided authorization callback but does not enforce field-level redaction, tenant isolation or external IAM. No UI should display evidence from this prototype without separate data-access controls.

## Integration direction

1. Adapt the **canonical** APX implementations behind versioned schemas; do not reimplement or self-certify them.
2. Add signed evaluator result binding, source version and PackSpec digest verification, plus mandatory obligation coverage before enabling any `ADMIT`.
3. Run cross-repository golden tests from ICEBERG/RegimeReader/APX and deceptive-witness fixtures.
4. Move physical persistence to PostgreSQL, with RLS and auditable append-only controls; maintain SQLite as a deterministic test adapter.
5. Benchmark vector-only, graph-only and QSS on identical constrained queries, tracking unsupported admissions, constraint retention, recall, latency and cost.
