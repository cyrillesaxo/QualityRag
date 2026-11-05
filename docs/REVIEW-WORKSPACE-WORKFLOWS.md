# Reviewed transformation and observation workflows in the workspace

The existing local Research Review workspace now exposes the reviewed activation
and source-observation workflows alongside branch review. Start it with the
existing `serve` command and host-owned public-key configuration. Browser tokens
are signed access tokens; no signing key is entered or generated in the browser.

## Run an already signed transformation

1. Open the workspace with a token granting read and write scopes.
2. Expand **Run a reviewed transformation**.
3. Select the exact original JSON source and its previously signed request file.
4. Select **Run signed transformation** to stage the source/artifact and run all
   release, reviewer, source, policy, preservation and fallback checks.
5. Inspect the actual result and trace, or download the complete receipt.

The source limit is 64 KiB and the request-file limit is 350,000 bytes; the total
HTTP request remains bounded by the existing 512-KiB limit. A workspace without
configured reviewer authority displays that limitation and hides the execution
form. Host configuration follows REVIEWED-ACTIVATION-WORKFLOW.md. Browser file
selection and pressing Run never create or substitute a release/review signature.

The result distinguishes finite preservation success, refusal without output, and
restoration of the authorized original after candidate failure. Domain admission
remains INCONCLUSIVE. A failed or invalid new request clears the previous result;
no stale success or output is presented as the new result. The downloaded receipt
uses the exact server response text, retaining JSON number spellings such as 1.0.
The raw signed request is also transmitted without browser reserialization.
Unsafe integer annotations/requests are refused; use Python for large integers.

## Stage and run through clients

POST /api/reviewed-run takes exactly base64 (original bytes) and request (the
existing activate-plan request). Both authenticated read and write scopes are
required before staging. The source hash must match the signed request. The
server stores source and canonical artifact in the authenticated tenant, then
calls the same activate-plan path; all existing release, review, policy, version
and persisted replay checks remain mandatory. It grants no new authority.
Staged inert objects can remain in custody even when later verification refuses.

~~~python
receipt = client.run_reviewed(raw_source, signed_request)
~~~

~~~typescript
const receipt = await client.runReviewed(sourceBytes, signedRequest);
~~~

~~~bash
python -m tools.activation_runtime.cli activate-plan \
  --endpoint http://127.0.0.1:8769 \
  --token access-token.json --request reviewed-request.json --source original.json
~~~

Without --source, the existing CLI behavior uses objects already in custody.
Tests compare Python, TypeScript and CLI across success, refusal and fallback,
and verify staging into a fresh empty object store. Browser numeric constraints
still apply to the TypeScript client's parsed request objects; signature or hash
mismatches refuse rather than authorizing a rounded representation.

## Inspect a source observation graph

Expand **Inspect a source observation graph**, choose either a UTF-8 source file
(up to 64 KiB) or an existing source hash, and load an observation draft file
(up to 250,000 bytes). Exactly one source selector is required. Drafts may include
a complete ID rename. The workspace shows node kinds, annotation values, role
bindings, quantities/units, exact quoted text, unknown domain validity and the
complete graph/transition receipt. Source annotations are rendered as text,
including strings that resemble HTML; they never become executable markup.

Read-only users can inspect an existing authorized source hash but cannot upload
or stage new source data. The full original remains required for residual/refetch;
a structurally checked graph does not validate annotation meaning or establish
canonical APX parity.

## Account switching and browser verification

Connecting another token clears loaded source-derived results, file inputs,
search text, pending previews and receipt buffers. Requests and file-reading
steps bind to the current workspace epoch. A delayed response from a prior token
is discarded before parsing/rendering, and a multi-step old operation cannot
continue uploading or acting under the new token. Tokens remain in memory rather
than persistent browser storage. This does not revoke an already issued token or
undo a server operation already authorized before switching.

Real Chromium checks cover the original branch preview/prune/reopen journey and
the new transformation/graph journeys: exact receipt download, rejected-request
state, read-only inspection, source-text injection safety, mobile width and a
held old-tenant response fulfilled only after switching tokens. These are local
software checks, not independent user evaluation or a production deployment.
