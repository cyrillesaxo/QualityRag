# Customer-signed protected Drive admission — narrow pilot

**Status: experimental, undeployed, single-process.** This workflow turns a *specific*
human-reviewed, signed source claim into a protected registry decision. It is not a
claim that the model independently understands the policy, that the original
publisher is authenticated, or that two signing keys guarantee two distinct people.

## What is verified and controlled

1. An approved PackSpec is resolved **server-side**, with its exact SHA-256 binding.
2. The authenticated requestor has `evidence.ingest`, `drive.reader`, and explicit
   `qualityrag_services` access to the protected service/environment.
3. Two **distinct trusted Ed25519 public keys**, configured out of band, verify the
   *same* `qualityrag.signed-observations/v1` payload using QualityRAG's
   QR-CJSON-1 canonical format. One key is designated **custodian** and one
   **meaningReviewer**.
4. The signed payload binds the owner identity digest, Drive folder, approved policy,
   source IDs, file revision digests, exact line digests, requirement mapping, asserted
   origin, support status, short validity period, and one-time nonce.
5. The registry **re-downloads the source bytes** from Google's API with current
   owner credentials, rechecks the file belongs to the selected folder, compares
   bytes to the signed/cached digest, and checks the owner has not excluded it.
6. After live file I/O, it rechecks the owner selection and approved PackSpec before
   recording a deterministic PackSpec result in the local protected-decision ledger.
7. A second implementation in Python verifies the signed envelope and supplied
   original bytes and independently reproduces the metadata decision.

**Boundaries:** A signer attests a claim; a signature is not a proof of the claim's
real-world truth. This v1 bridge only supports PackSpecs with
`min_independent_sources=1` (or omitted) and **no `max_age_seconds`** because
source intellectual independence and original publication freshness are not yet
demonstrated. Other PackSpecs fail closed. `ADMIT` means **authorized to use a
customer-signed human-reviewed assertion** in this registry, not unrestricted AI
inference or a regulatory certification.

## Operator setup — public keys only

Enable the existing OIDC + encrypted, per-user Drive configuration, selected-folder
index, evidence ledger, and explicit protected service list as described in
[Protected Drive ingress](PROTECTED-DRIVE-INGRESS.md).

Generate **two different Ed25519 key pairs** in separate custodian-controlled
environments. Example on a development machine:

```sh
openssl genpkey -algorithm Ed25519 -out custodian-private.pem
openssl pkey -in custodian-private.pem -pubout -out custodian-public.pem
openssl genpkey -algorithm Ed25519 -out reviewer-private.pem
openssl pkey -in reviewer-private.pem -pubout -out reviewer-public.pem
chmod 600 custodian-private.pem reviewer-private.pem
```

The private keys must **never** be copied into QualityRAG Studio, the registry,
the repository, Wix, browser storage, or a support ticket. Distribute approved
**public** keys using an independently controlled trust channel. Create a private
operator JSON configuration with this exact format:

```json
{
  "custodian": {
    "keyId": "customer-custodian-2026",
    "publicKeyPem": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"
  },
  "meaningReviewer": {
    "keyId": "customer-meaning-reviewer-2026",
    "publicKeyPem": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"
  }
}
```

Use actual valid PEM contents, not the ellipsis in this example. On the
**single-instance registry server**, configure:

```sh
export QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE="/secure/trusted-review-public-keys.json"
```

Restart after adding or revoking keys. The server refuses a trust configuration
where the two roles use the same key material or key ID. **Different keys do not
automatically establish different human reviewers**; the customer must govern who
actually controls each key. Keep key provenance, rotation, compromise reporting
and authorized reviewer rosters outside this local prototype.

## Customer review workflow (example for one exact source)

First, sign in to Studio through a verified owner OIDC identity and connect the
owner's Google Drive. Select a non-root folder, explicitly synchronize the
documents, and find the source in **Evidence visibility and owner control**.
Inspect the governing PackSpec and underlying original text.

Prepare one **unsigned** review payload using the exact source bytes obtained
through an authorized, independently controlled copy. Source IDs, folder IDs,
policy digests and the subject binding must be from **this** user and **this**
service. The command is illustrative—replace all identifiers and paths:

```sh
python tools/packspec_compiler/prepare_protected_drive_review.py prepare \
  --service claims-api --environment dev \
  --policy-sha YOUR_64_HEX_POLICY_DIGEST \
  --owner-subject "YOUR_VERIFIED_OIDC_ISSUER#YOUR_SUB" \
  --folder-id YOUR_SELECTED_DRIVE_FOLDER_ID \
  --source-id google_drive/YOUR_32_HEX_SOURCE_ID \
  --requirement-id YOUR_APPROVED_REQUIREMENT_ID \
  --origin org_YOUR_APPROVED_32_HEX_ORIGIN \
  --line-number 1 --status SUPPORTS \
  --source /customer/original/policy.txt \
  --out prepared-human-review.json
```

The default `--status UNKNOWN` avoids implicit approval; use `SUPPORTS` **only**
when reviewers actually confirm semantic support. The custodian independently
checks source identity, bytes and asserted origin. The meaning reviewer separately
checks whether the exact line actually supports the specified PackSpec requirement
and whether omitted context or exceptions undermine it.

**Each signer receives the exact same prepared file**; neither needs to share
its private key. On two appropriately controlled systems:

```sh
python tools/packspec_compiler/prepare_protected_drive_review.py sign \
  --role custodian --payload prepared-human-review.json \
  --private-key /secure/custodian-private.pem \
  --key-id customer-custodian-2026 \
  --attest-reviewed --out customer-custody.json

python tools/packspec_compiler/prepare_protected_drive_review.py sign \
  --role meaningReviewer --payload prepared-human-review.json \
  --private-key /secure/reviewer-private.pem \
  --key-id customer-meaning-reviewer-2026 \
  --attest-reviewed --out meaning-review.json
```

Assemble the transport package without private keys:

```sh
python tools/packspec_compiler/prepare_protected_drive_review.py build-request \
  --custody customer-custody.json --meaning meaning-review.json \
  --request-id customer-review-001 --trace-id trace-001 \
  --out signed-protected-request.json
```

Within the signed payload's five-minute validity window, paste the JSON into
Studio's **Customer-signed protected evidence review** panel and submit.
Alternatively, use a requestor bearer token with the owner OIDC subject,
`evidence.ingest` and `drive.reader` roles to POST the exact JSON to
`/v1/evidence/protected-admit`.

An included, current source with matching live bytes, two trusted signatures and
a satisfied single-origin policy may produce `ADMIT` (HTTP 201).
Contradictions yield `REFUSE`; insufficient obligations yield `INCONCLUSIVE`
(HTTP 200). All valid signed decisions use a durable single-use nonce; replaying
a previous signed request produces HTTP 409.

**Owner exclusion**, an outdated revision, Google revocation, an unknown policy
requirement, a mismatched owner/folder, signer substitution, expired approvals or
an unsupported PackSpec all fail closed.

### Withdraw one review decision

When an accepted interpretation or custody approval becomes disputed,
the same source owner can withdraw **that particular decision** in
Studio. An owner identity with both `evidence.reviewer` and
`drive.manager` may call
`POST /v1/evidence/protected-decisions/{id}/revoke` with
`{"reason":"REVIEW_DISPUTED"}`. This appends a local decision
revocation without deleting or excluding the original Drive document.

Old receipts remain historical evidence of what reviewers signed;
`POST /v1/evidence/protected-decisions/{id}/use-check` refuses
the withdrawn decision, including for requests in progress
before the final synchronous permit record. Reapproval requires
a new, separately signed decision.

[Detailed withdrawal controls and live use contract](PROTECTED-EVIDENCE-USE.md).

## Independent customer verification

Export the signed protected receipt from Studio using the **same authenticated
source-owner identity**. A third party, given approved public keys, the original
source bytes, and the correct owner subject and folder identity, can run:

```sh
python tools/packspec_compiler/verify_protected_drive_receipt.py \
  --receipt signed-protected-receipt.json \
  --trust /reviewer-trust/trusted-review-public-keys.json \
  --owner-subject "YOUR_VERIFIED_OIDC_ISSUER#YOUR_SUB" \
  --folder-id YOUR_SELECTED_DRIVE_FOLDER_ID \
  --source google_drive/YOUR_32_HEX_SOURCE_ID=/reviewer/exact/policy.txt
```

It verifies independent Ed25519 signatures, exact byte and line hashes,
owner/folder/PackSpec binding, and a separately recomputed v0.1 verdict.
**It does not reproduce historical Google OAuth authorization**, independently
prove publisher identity, verify the humans' identities beyond their trusted
role keys, or authenticate the local ledger's external timeline.

The exported receipt includes signed metadata and digests, **not the document
text**. Handle it as potentially sensitive metadata, and use an offline reviewer
when documents cannot leave the customer's environment.

## Fresh permission before any downstream use

The signed receipt above is a historical review result. It **does not**
grant a permanent authorization to use the source. An integrated app must
run a fresh `POST /v1/evidence/protected-decisions/{id}/use-check` for
each proposed answer, providing an unused request ID and only the
SHA-256 digest of the answer bytes. The registry rechecks both
signatures (including expiry/revocation), current PackSpec and
the owner-controlled source against live Google file bytes.

The TypeScript `ProtectedUseClient.releaseAnswer()` is a fail-closed
integration example. Studio offers a **Check live evidence-use permission**
demonstration in the protected admission panel; it never sends the
drafted answer text to the registry. If the customer excluded
the source, Drive access vanished, the file changed or the
policy was rebound, the old receipt is denied. Historical independent
replay can still succeed on original bytes; this does **not** contradict
current revocation.

[Live evidence-use API, response-release example and limits](PROTECTED-EVIDENCE-USE.md).

## Acceptance and release gates

Reproduce the following before a real pilot: a valid approval, source exclusion,
a modified Google document, a revoked credential, incorrect owner/folder,
wrong signer, disagreeing signers, expired attestation, reused nonce, changed
PackSpec, unsupported source-age requirement and independent Python replay.
Keep signed review keys separated from account operators.

**Not production-ready:** The local Drive cache and evidence ledger are
single-instance; there is no external audit anchor, multi-tenant key lifecycle,
real customer acceptance, signed PackSpec approval at this precise bridge,
or universal integration into arbitrary RAG inference/answer pipelines.
