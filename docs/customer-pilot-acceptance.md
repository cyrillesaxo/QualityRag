# QualityRAG Studio — customer-operated acceptance pilot

**Current status: NOT ACCEPTED.** This is a reproducible protocol, not evidence that a real customer completed it. Synthetic CI can test code and evidence-packet validation, but it cannot establish customer identity, real Google permissions, independent security approval, or deployment readiness.

## Purpose and ownership

The customer's operator chooses the Drive account and folder, excludes documents, inspects the decision and controls, and withdraws authorizations. Two **independent human roles** review source-custody and meaning claims. A separate security reviewer validates the intended environment and access boundaries. QualityRAG does not certify an owner's semantic claims as objectively true.

Production Google Drive read-only access may involve restricted OAuth scopes. Do not deploy the connector or give test credentials until the customer has reviewed scopes, data processing and retention, token storage, the security boundaries, and any necessary provider verification.

## Preflight — do not shortcut

1. Pin the **exact** deployed Registry, Studio and SDK commit SHA, environment, configuration revision and a rollback method. Verify deploy artefacts match the candidate SHA. Record the deployed base URL and time.
2. Confirm independent OIDC token validation and the exact `qualityrag_services` authorization claim. The Registry must refuse unauthorized roles, missing owner scope, and unknown service/environment. Do not substitute the local bearer token.
3. Enable the Google adapter, encrypted customer credential storage, owner-specific index and signed-review trust keys **only in the approved pilot environment**. The default CLI Registry does not instantiate these services. Verify the service is fail-closed if any component is missing.
4. Use a customer-owned, non-sensitive test folder of source files with a primary clause, a distant exception, and a contradictory second file. Record only source identifiers and digest metadata in the evidence packet, not OAuth tokens, private keys or original sensitive documents.
5. Customer and independent security reviewer confirm written scope, permitted data, test-user roles, retention/deletion, observability, and rollback. An unapproved environment is a failed preflight.

## Seven test scenarios

| ID | Customer action | Required observed behavior |
| --- | --- | --- |
| A1_OWNER_DRIVE_SCOPE | Connect a customer-owned account, explicitly select the permitted folder, exclude one file, sync and inspect visibility | Only permitted files appear in scoped index; no indexing on connection; no cross-account visibility |
| A2_DISTANT_EXCEPTION_DENIAL | Sign a governing clause but leave a distant exception unreviewed | Grounded delivery refuses with an exception/coverage reason; no answer text leaks |
| A3_INDEPENDENT_SIGNED_REVIEW | Two independent role keys approve the exact bounded clause package; validate the receipt offline | Source/custody digest, PackSpec binding, independent signatures and exact byte verification match; extract contains only human-reviewed source lines with uncertainty labels |
| A4_CROSS_DOCUMENT_CONFLICT | Include an opposite payer/payee obligation or negated payment from a second source | Unresolved relation candidate blocks grounded release, even if both clauses are signed; unsupported paraphrase remains UNKNOWN |
| A5_REVOCATION_AND_MUTATION | Withdraw a decision, alter the original source after signing, or exclude it mid-workflow | Subsequent use and grounded delivery are refused, with no response content; replay fails |
| A6_TENANT_ISOLATION | Use a second customer identity, wrong service scope, read-only role attempting a manager action and local bearer credentials | Unauthorized requests denied without cross-owner document/receipt/identity disclosures |
| A7_TELEMETRY_AND_COVERAGE | View Studio evidence feed, replay, status, refusal, source scope, unknowns, and operator controls | Distinguishes attempted, denied, reviewed, released, incomplete, and absent events; never claims global application monitoring or semantic completeness |

A scenario is **PASS** only when the customer operator has actually performed it on the pinned environment and the captured artifact supports the observed result. An HTTP 200, simulated provider, or green unit test alone is insufficient.

## Evidence packet

Place `packet.json` and **redacted** proof artifacts beneath a dedicated folder. Required schema:

```json
{
  "schema": "qualityrag.customer-pilot-evidence/v1",
  "pilotId": "CUSTOMER-TEST-01",
  "customerOperator": "Customer-confirmed operator identifier",
  "targetEnvironment": "Customer-approved deployed environment URL",
  "candidateCommitSha": "40-character git commit sha",
  "runStartedAt": "2026-11-09T11:00:00.000Z",
  "runCompletedAt": "2026-11-09T12:00:00.000Z",
  "scenarios": {
    "A1_OWNER_DRIVE_SCOPE": {
      "status": "PENDING",
      "artifact": "proofs/a1-redacted.json",
      "sha256": "SHA-256 of the evidence artifact"
    }
  },
  "securityReview": {
    "status": "PENDING",
    "reviewer": "Independent reviewer identifier",
    "artifact": "proofs/security-approval.txt",
    "sha256": "SHA-256 of the evidence artifact"
  },
  "customerSignoff": {
    "status": "PENDING",
    "reviewer": "Customer approver identifier",
    "artifact": "proofs/customer-approval.txt",
    "sha256": "SHA-256 of the evidence artifact"
  }
}
```

Populate all seven scenario keys with `status: "PASS"` and correct artifact SHA-256 values **only after** the observations exist. Set `securityReview` and `customerSignoff` to `APPROVED` only with the actual independent and customer approvals.

To check structural completeness and local digest integrity:

```bash
node scripts/customer-pilot-gate.mjs /path/to/redacted-pilot/packet.json
```

The validator returns `READY_FOR_INDEPENDENT_HUMAN_AUDIT` for a complete packet. **It always returns `pilotAccepted:false`.** A separate authorized human security reviewer and the actual customer decide acceptance after checking source authenticity, record signatures, protocol adherence, and deployed environment. Do not treat a structurally valid synthetic packet as acceptance.

## Exit and rollback

Acceptance requires all seven demonstrated scenarios, independent security review, real customer signoff, and a recorded rollback/retention decision. If any scenario is unverified, the pilot stays NOT ACCEPTED. Unplug credentials/disable connector routes, revoke test tokens, delete customer-scoped index as authorized, and retain only customer-approved redacted evidence after ending the pilot.

Tracked in [release recovery issue #100](https://github.com/cyrillesaxo/QualityRag/issues/100).
