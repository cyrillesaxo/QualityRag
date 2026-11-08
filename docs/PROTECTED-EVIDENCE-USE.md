# Protect the last mile: live evidence-use checks (experimental)

**Status:** Draft / research pilot, unmerged and undeployed. This is an
**opt-in integration contract**, not a universal answer gate or claim that
QualityRAG can independently certify AI-generated text.

## Why a valid signed receipt is not a perpetual permit

A customer may approve a specific signed source assertion at 12:00 and
exclude that document at 12:01. An AI application using the old stored
`ADMIT` from 12:00 would violate the customer's current choice.

**A static receipt supports historical replay. It does not authorize use now.**

The new endpoint revalidates current permissions, exact Google bytes, the
governing PackSpec, both customer-selected role keys, and the source
owner's exclusion state every time an *integrated* application wants
to rely on a previously admitted signed assertion.

## API — require a fresh decision-use permit

`POST /v1/evidence/protected-decisions/{decisionId}/use-check`

Prerequisites: a verified OIDC user with **both** `evidence.ingest` and
`drive.reader`, explicit `qualityrag_services` membership in the
decision's current `serviceId@environment`, the same owner subject that
recorded the original decision, a protected service still enabled, and
an approved PackSpec unchanged from the decision.

Request body (do **not** upload the answer text):

```json
{
  "requestId": "customer-inference-0001",
  "answerSha256": "9fc2f1b8bf72ed52a4ff3cb1cb27ce7b913a9d36e5b0a6f3e8ee6137a84b4ab3"
}
```

Use the real SHA-256 digest of the exact UTF-8 bytes of the answer you
intend to release; the digest shown above is only an example. The
request ID must be unique for each attempted use.

The endpoint refuses unless **all** requirements hold:

- The existing decision belongs to the current authenticated user,
  is for an authorized, still-protected service, and was actually
  `ADMIT` rather than `REFUSE` or `INCONCLUSIVE`.
- The registry-resolved approved PackSpec is still the exact version
  bound to the decision, including its SHA-256.
- Both custodian and meaning-reviewer signatures are still trusted
  under the *current* public-key trust configuration, agree on the
  same assertions, and remain in the narrow validity window.
- The customer's current Google Drive connection and selected folder
  still authorize the source. Exact live Google bytes and anchored
  line hashes still match.
- The customer has not excluded the source, including while the Google
  download was in progress. The registry checks the owner-controlled
  snapshot **again after** the provider I/O.
- The previously recorded deterministic PackSpec result matches a new
  evaluation of the signed assertions and the fresh source check.
- The same request ID has not previously been permitted; successful
  permits are rate-limited and appended to the local hash-chained
  evidence ledger.

The response has schema `qualityrag.protected-decision-use/v1` and
`permission=PERMIT_SIGNED_ASSERTION_USE`, with the decision ID,
request ID, exact answer digest, local receipt ID, policy digest and
checking time. The flags `answerSemanticsVerified=false`,
`independentPublisherVerified=false`, `externallyAnchored=false`
and `globalEnforcement=false` are mandatory, not cosmetic.
The header is `Cache-Control: no-store`.

A prior permit is not authorization for another answer or future
request. A model can still produce an unsupported answer despite
having access to accurately admitted evidence: this endpoint does
**not** assess the model's prose.

## A fail-closed TypeScript delivery integration

The TypeScript SDK exposes `ProtectedUseClient`:

```ts
import {ProtectedUseClient} from '@qualityrag/sdk';

const guard = new ProtectedUseClient(
  process.env.QUALITYRAG_REGISTRY_URL!,
  ownerScopedOidcToken
);

// Keep answer private until the registry has freshly rechecked
// the signed evidence, policy, source owner and live provider bytes.
const {answer: deliver, receipt} = await guard.releaseAnswer(
  signedDecisionId,
  uniqueRequestId,
  modelDraft
);

// Only the exact digest-matched answer is released on a valid permit.
return deliver;
```

The helper calculates the UTF-8 SHA-256 digest locally; sends only
the digest and request ID; rejects non-HTTPS remote endpoints,
redirects, failed/malformed/mismatched permits, and network errors.
An application must call it **at the point of release**, fail closed,
not cache previous permits, and prevent other codepaths from returning
the raw model draft.

Studio has a **Check live evidence-use permission** control in its
signed-review panel. It keeps a proposed answer in the browser and
sends only its digest, displaying a scoped permit or explicit
failure. This UI is a demonstrator, not an enforcement proxy for
arbitrary customer traffic.

## Runnable demonstration and adversarial tests

```sh
npm --prefix apps/registry install
npm --prefix apps/registry run admission:demo
npm --prefix apps/registry test
npm --prefix sdk/typescript install
npm --prefix sdk/typescript test
```

The synthetic real-HTTP demonstration shows:

1. Signed human-reviewed evidence `ADMIT`.
2. A request-specific use permit for an answer digest.
3. Duplicate use request ID rejected.
4. User excludes the source.
5. The previously admitted evidence receipt is now **unusable**.
6. Independent Python verifier still reproduces the *historical*
   evidence decision from exact original bytes. This is not a
   contradiction: historical reproducibility differs from current
   authorization.

Additional tests cover current service scope and owner roles,
changed source bytes, revoked Drive access, stale snapshots,
changed PackSpec, a non-admitted receipt, and owner exclusion while
a provider download is in flight. Generic unreviewed evidence
ingestion remains blocked for protected services.

## Revoke one approval without hiding the underlying document

A source owner may wish to withdraw a particular review without
excluding the entire document from search (e.g., a previously accepted
interpretation is disputed). This is a distinct **decision-level control**.

`POST /v1/evidence/protected-decisions/{decisionId}/revoke` requires
**both** `evidence.reviewer` and `drive.manager` under the
*same source-owner OIDC subject* and service scope. The bounded request:

```json
{"reason":"REVIEW_DISPUTED"}
```

Allowed reason codes: `OWNER_WITHDRAWN`, `REVIEW_DISPUTED`,
`CUSTODY_DISPUTED`. The registry appends a local
`protected-revocation` event containing only scope, decision ID,
actor hash, time and reason. Revocation is **permanent within the
ledger**; reapproval requires a new two-signature decision.

`GET /v1/evidence/protected-decisions/{decisionId}/status`
allows an authorized source owner to inspect the current revoked
state. The status endpoint **never** reports current use as
automatically authorized: a live use check is always required.

Every use-check examines the latest revocation records **twice**:
before expensive Google I/O and during the synchronous final ledger
append. A source can remain searchable, and the historical signed
review remains independently replayable, while all future
permissions for that revoked decision are denied. Studio displays
withdrawal controls and an observed revocation counter.

No automatic un-revoke or self-approved override is offered. A
privileged filesystem operator could still tamper with the local,
unanchored ledger; production external anchoring and durable custody
remain necessary.

## Explicit limitations

- Only **integrated applications** are guarded. A separate model,
  direct database query, legacy endpoint on an unprotected service,
  or external agent that ignores the SDK can still bypass this pilot.
- The guard does not inspect answer semantics. A malicious or
  incompetent application could attach a valid evidence receipt to
  a misleading answer. Genuine answer-level entailment and completeness
  checking are separate research work.
- A permit can become stale immediately after it is returned if
  source access changes. For production delivery, an application
  needs a controlled gateway with transactional output release,
  a bounded response TTL and stronger revocation propagation.
- Current OIDC Google integration and local ledger are single-instance,
  not multi-tenant regulated production architecture. The ledger
  has no independent time anchor.
- Two role keys do not prove two distinct humans; role assignment
  and key provenance require real customer approval.
- The signature bridge is deliberately unable to prove original
  publication time, independent intellectual origin, or
  objective factual/semantic truth.

**Evidence credibility:** show the original claim; demonstrate who
reviewed it; re-check whether the owner permits it **now**; provide a
reproducible receipt; state precisely what remains unknown.
