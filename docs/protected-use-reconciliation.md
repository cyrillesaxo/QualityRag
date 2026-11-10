# Protected-use reconciliation (read-only, proposed integration)

**Status:** Source change prepared but unbuilt and unverified. Do not claim production deployment or current source revalidation.

QualityRAG records a protected-use audit event when `POST /v1/evidence/protected-decisions/{id}/grounded-deliver` succeeds. The event persists a digest of its `requestId`, scoped to the protected decision's owner, service and environment. When a caller loses the HTTP response after this append, it cannot safely retry the stateful use.

To support Balafons US-066, the Registry now exposes the proposed **read-only** endpoint:

`GET /v1/evidence/protected-decisions/{decisionId}/use-status?requestId=delivery-<uuid>`

The Registry requires a verified OIDC identity with `evidence.reader`, a matching `qualityrag_services` scope, and ownership of the protected decision. It searches the append-only ledger for the **exact** request digest and returns one of:

- `RECORDED`: a matching protected-use event exists. Only the use receipt identifier, answer/policy SHA-256, delivery mode and recorded time are returned; never source text or answer content.
- `NOT_RECORDED_AT_CHECK_TIME`: no matching event was visible at the instant of this query. The original request may still be executing; **retry is never authorized**.

All responses set `retryAuthorized:false`, `currentSourceRevalidated:false`, `releasePermitted:false`. Requests for foreign decisions and improperly scoped subjects return 404 or 403 without disclosing their audit events. The endpoint performs **no** Google Drive read, new source evaluation, new use event, or approval.

A Balafons client may use `RECORDED` to reconcile its local `UNCERTAIN` state to `REMOTE_RECORDED`, while preserving the absence of a received answer. `NOT_RECORDED_AT_CHECK_TIME` must retain the local uncertainty; a later audited operator investigation is required before any new independently approved use request.

**Remaining before acceptance:** tests/CI, deployment to a real OIDC-protected Registry, source/no-answer leak checks, operator audit, rate limits, concurrent in-flight request behavior and staged customer pilot. This is a compatibility protocol, not globally exactly-once semantics.
