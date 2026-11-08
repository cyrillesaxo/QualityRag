# Protected response gateway: enforce authorization at output release

**Status: research pilot only; PR #85 is draft, unmerged and undeployed.**

The previous `use-check` API returned a permission and relied on an
integrated application to withhold its draft until that permission
arrived. That is useful but leaves an integration mistake possible.

The **buffered delivery endpoint** makes the registry own both the
proposed answer and the authorization decision for **that one response**.

## Exact contract

`POST /v1/evidence/protected-decisions/{decisionId}/deliver`

The caller is an authenticated source owner with both `evidence.ingest`
and `drive.reader`, signed service/environment scope and a previously
signed human-reviewed `ADMIT` decision. This endpoint accepts:

```json
{
  "requestId": "inference-0001",
  "answer": "Synthetic answer for the controlled gateway."
}
```

- `requestId` is an unused bounded ID for each attempted delivery.
- `answer` is a **nonempty UTF-8 string of at most 16 KiB**. NUL
  characters, unbounded or extraneous fields, and oversized
  requests fail closed.
- The registry calculates the answer SHA-256 itself; the caller cannot
  attach an arbitrary precomputed digest to different answer bytes.
- Before releasing the response, the registry checks the same
  dual role signatures, current signed-owner Drive access, exact
  live Google bytes, selected source exclusions, approved PackSpec,
  admission status, outstanding review revocations, and request replay
  controls as `use-check`.
- Successful checks create a **metadata-only**, local
  `protected-use` ledger entry tagged
  `deliveryMode=SERVER_BUFFERED_RELEASE`. The ledger contains the
  answer digest and authorization metadata but **not the answer
  text**.
- Then, in the same server turn with no additional asynchronous
  execution, the registry returns
  `qualityrag.protected-answer-delivery/v1` containing the **exact
  buffered answer** and a matching use receipt. The HTTPS response
  uses `Cache-Control: no-store` and JSON encoding.
- Denied requests **never** echo the answer. They return a bounded
  error reason; a caller must not fall back to an unprotected route.

This is a buffered gateway, not a streaming token gateway.
Streaming a draft to a user before authorization would defeat the
control.

### Customer-owned privacy boundary

**The buffered gateway necessarily receives the entire proposed
answer in plaintext.** It is suitable for deployment inside a
customer-operated/private application boundary. Do **not** send
protected data through a third-party demonstration endpoint or
assume this implementation has a production privacy assessment.

The preexisting `use-check` path remains available for applications
that cannot share answer text. It sends only a SHA-256 digest, but
depends on the consuming application to enforce release locally.
The telemetry separates `SERVER_BUFFERED_RELEASE` from
`DIGEST_ONLY_CLIENT_RELEASE`.

An issued permit is not proof that a client actually received the
response: network termination can occur after ledger append.

## TypeScript integration

```ts
import {ProtectedUseClient} from '@qualityrag/sdk';

const guard=new ProtectedUseClient(
  'https://your-customer-hosted-qualityrag.example',
  ownerScopedOidcToken
);

// Never write modelDraft to the user, websocket, logs, analytics,
// or another output channel before this call completes.
const delivered=await guard.deliverViaGateway(
  signedDecisionId,
  uniqueRequestId,
  modelDraft
);

// This value was returned by the registry *only* after its
// current evidence-use check and exact byte matching.
return delivered.answer;
```

The SDK checks the returned answer equals the draft and verifies
the permission, answer digest, request ID, decision ID, exact
`SERVER_BUFFERED_RELEASE` mode, schema, and limitation flags.
A denial, network failure, malformed response or mismatch throws
instead of releasing the draft.

An application must **not** log or stream its draft elsewhere
before this call; the gateway cannot prevent a rogue or unintegrated
application from bypassing it.

## Demonstrate rather than persuade

```sh
npm --prefix apps/registry install
npm --prefix apps/registry run admission:demo
npm --prefix sdk/typescript install
npm --prefix sdk/typescript test
```

The synthetic real-HTTP demonstration and adversarial tests cover:
a valid admitted human claim, exact buffered answer release, request
replay denial, another owner or missing role, unacceptable payloads,
changed Google bytes, policy rebinding, consent exclusion and
independent reviewer withdrawal.

A source excluded **while Google is queried** cannot be used even if
its historical admission was valid. Denied responses contain no
draft text; local telemetry contains only answer digests and fixed
authorization metadata.

### Studio

The **Customer-signed protected evidence review** panel offers both
a digest-only check and an explicitly labeled buffered-gateway test.
Using the buffered option requires checking an opt-in acknowledgement
that the draft **will be transmitted to the configured registry**.
The UI does not silently convert digest-only checks to plaintext.

## Optional exact-source output instead of arbitrary model prose

`POST /v1/evidence/protected-decisions/{id}/grounded-deliver`
accepts **only** a unique request ID. The server revalidates
the live owner source and PackSpec, then builds a fixed extract
from **all human-signed SUPPORTS lines**, plus explicitly
unreviewed adjacent context. The output is tagged
`SOURCE_GROUNDED_EXTRACT`, and no user-authored draft can be
added to the request.

A known exception whose signed witness is required by the
PackSpec cannot be silently dropped. However, a distant or
unknown exception elsewhere in the document remains unresolved;
this is exact extraction, not unrestricted semantic verification.

[Acceptance protocol and caveats](SOURCE-GROUNDED-ANSWERS.md).

## Production release blockers

1. **Answer semantics remain unverified.** A signed evidence source
   does not prove the proposed answer entails every governing rule
   or acknowledges every hidden exception. More evidence witnesses,
   PackSpec obligations and answer-level tests are necessary.
2. **No universal downstream enforcement.** A customer must route
   all output through the gateway; direct LLM responses, alternate
   APIs, external SDKs and streaming transports can bypass it.
3. **No externally anchored audit log or distributed transaction.**
   The local ledger has limited multi-instance integrity and cannot
   conclusively prove network delivery. Revocation can happen after
   successful response release.
4. **No production security/privacy assessment.** Token lifecycle,
   transport TLS, deployment trust, tenant separation, key rotation,
   incident response, content handling, rate limiting and provider
   access are pilot assumptions.
5. **No original publisher or true human-independence proof.** The
   human-signed source custody and semantic assertions are still
   bounded customer attestations.
6. **No certified compliance claims.** This is an observable,
   customer-controllable research enforcement boundary.

The customer acceptance challenge should be:

> Approve a synthetic policy, submit a draft through the gateway,
> then exclude the source or revoke the decision. The next draft
> must never be returned, and Studio must show why.

**Credibility is visibility and control, not a badge saying “secure.”**
