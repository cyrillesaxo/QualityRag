# QualityRAG Evidence Assurance: show, then challenge

This prototype adds an Evidence Assurance panel inside the existing QualityRAG Studio UI. It is intentionally a local, synthetic demonstrator, **not production telemetry**.

The existing QualityRAG Python metadata evaluator returns per-requirement verdicts (ADMIT, REFUSE, INCONCLUSIVE), independent-origin counts, and failure reasons. Current Studio manages policy drafts, approvals, service bindings and Semantic Store exploration but does not show customer-facing evaluation traces.

## Acceptance workflow

1. Choose an illustrative decision and its governing PackSpec requirement.
2. Inspect evidence metadata, declared origin counts, reasons, and the initial gate verdict.
3. Switch to a changed evidence set. Compare the result. The browser displays stored synthetic SDK-style results and does not execute the evaluator.
4. The customer role can accept or dispute the *finding*, with a rationale. This never modifies the policy gate's verdict.
5. Export a synthetic, unsigned receipt. Browser review state is transient, not production persisted or customer authenticated.

## Required telemetry contract before production

- Evaluation: request and trace ID, UTC timestamp, service and environment, tenant-bound PackSpec ID/version/digest, SDK version, obligation IDs and statuses, verdict and reason codes.
- Provenance: opaque source identifiers, verified/declared origins clearly distinguished, source revision and freshness, typed relationships and missingness. Avoid raw documents, prompts, secrets, PAN and PII.
- Coverage: instrumented requests / eligible requests; unobserved does not mean compliant.
- Replay: a bounded replay request pins source versions, evaluated metadata, policy, evaluator version and clock. Compare exactly what changed; no automatic source-truth inference.
- Customer acceptance: authenticated reviewer with scoped RBAC, signed or append-only records where required, accepted / disputed / escalated / superseded states, dispute reasons and independent reproduction outcomes.
- Metrics: distribution of outcomes, consequential omissions (customer classified), false block rate on adjudicated reviews, median time to a reproducible proof, accepted vs disputed findings, cost of reviewer setup and replay.

Security: do not send customer content to a shared dashboard by default. Encrypt and separate tenant telemetry, minimize identifiers, enforce bounded retention, authorization and access logging. A browser-produced JSON receipt is NOT a digital signature, a proof of policy completeness, or a compliance certificate.

## Limits

No live event collector, OpenTelemetry export, persistent approvals, independently authenticated source provenance, cross-tenant security or customer acceptance signing is implemented here. It is a visual and interaction prototype for a real Studio backend integration.

Run the existing Studio via npm --prefix apps/studio run dev and inspect the Evidence Assurance panel.
