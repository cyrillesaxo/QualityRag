# Credibility = Visibility + Control — QualityRAG Studio acceptance contract

**Status:** Local pilot contract, not production certification or a claim that source contents have been authenticated.

A customer must be able to **see what the system has done**, **constrain what it is allowed to do**, and **reproduce a disputed finding**. Confidence scores, persuasive narration and polished dashboards are not substitutes.

## Observable facts and customer controls

| Customer question | Visibility delivered by the pilot | Owner control | Boundary |
|---|---|---|---|
| Which Google account and folder am I using? | Connected account, explicitly selected folder, OAuth scope disclosure | Connect, change folder, disconnect | Google's `drive.readonly` grant is account-wide; selected folder is enforced by application code |
| What was ingested? | Snapshot time, per-source name/type, pseudonymous source ID, revision digest, extracted lines | Explicit sync only | Direct children of selected folder; bounded formats and sizes |
| What was **not** ingested? | Per-file `UNSUPPORTED`, `EMPTY`, `FAILED`, `TOO_LARGE`, `TRUNCATED` status; partial coverage counts | Review source inventory; choose a different folder or fix files and resync | Does not prove every file in Google Drive was considered |
| Can I prevent a source from appearing in search? | Each source's `searchable` flag, owner reason code and local activity timestamp | Exclude/include an indexed source; owner exclusion survives resync, including content revisions | Exclusion suppresses lexical results but retains encrypted local text until whole-index deletion |
| Can I erase my cached content? | Indexed/not indexed state | Delete local index, disconnect, switch folder; generation fence blocks stale sync resurrection | Does not delete Google originals or independently saved exports |
| Can I verify a claim? | Search line/revision, original Google link, and *separate* Evidence Assurance replay/receipt | Open original, dispute evidence, export independent replay, arrange signed custody | Lexical search neither validates source authenticity nor produces PackSpec admission |

### Implemented owner API

- `GET /v1/drives/google/visibility` — OIDC `drive.reader`; returns the currently selected folder's encrypted-index inventory, partial-coverage reasons, owner selection state and bounded local control history. Raw source text and OAuth tokens are not in this response.
- `POST /v1/drives/google/source-control` — OIDC `drive.manager`; accepts **exactly** `{"sourceId":"google_drive/…","searchable":false,"reason":"OUT_OF_SCOPE"}` or explicit re-inclusion with `"searchable":true,"reason":"OWNER_SELECTION"`.
- User identity is always derived from the verified OIDC subject, never from request JSON. An account cannot change another account's indexed sources.
- Both APIs fail closed when per-user indexing is disabled or the caller has no appropriate role.

### Source-level control semantics

**Default:** Following a user-initiated sync, successfully indexed text is searchable in that same authenticated user's local index; it is **not** approved for evidence review.

**Exclude:** The source stops appearing in lexical search immediately. The user's exclusion reason is captured in the same AES-GCM-encrypted local snapshot. Exclusion persists on subsequent syncs even when source text changes. A different user cannot alter the setting.

**Include:** The owner explicitly restores a source to private lexical search. This changes no underlying PackSpec, original Drive permission, evidence provenance, or customer acceptance record.

**Erase:** `Delete my local index` removes the entire encrypted local index; the file content cannot be recovered using this application unless the owner explicitly syncs it again. There is no selective per-file permanent purge in this version. Exclusion **is not deletion**. Saved exports and system backups are outside this prototype's deletion guarantee.

**Activity:** Studio displays only a bounded, local, user-specific operational history. It is **not** an externally anchored audit log, regulator-approved evidence trail, or cryptographic proof of human identity.

### Governed Drive candidate check: owner control is enforced server-side

The private Drive source toggle now has a **policy-bound enforcement point** in addition to lexical search. An authorized user can select a source, choose an approved PackSpec requirement and click **Check candidate** in Studio. The registry **resolves the approved PackSpec itself**; the browser cannot substitute a policy or verdict.

The API requires the signed OIDC identity to have **both** `drive.reader` and `evidence.reader`, plus `qualityrag_services` authorization for the selected `serviceId@environment`. The current Drive user identity is never an input field.

- `GET /v1/drives/google/governed-requirements?serviceId=claims-api&environment=dev`: only IDs of approved, bound requirements and the policy digest are shown.
- `POST /v1/drives/google/governed-check`: bounded request `{"serviceId":"claims-api","environment":"dev","candidates":[{"sourceId":"google_drive/…","revision":"64hex","requirementId":"governing-rule","lineNumber":1}]}`.
- A candidate explicitly excluded by its authenticated owner receives `REFUSE` with `SOURCE_EXCLUDED_BY_OWNER`.
- A source not found in the current user's selected index, stale index, changed source revision, invalid line anchor, or missing index **cannot be admitted** and returns `INCONCLUSIVE` with a specific reason.
- An included source is still `INCONCLUSIVE`, with explicit `SEMANTIC_SUPPORT_NOT_VERIFIED` and `SOURCE_PROVENANCE_NOT_VERIFIED` reasons. **Being retrievable is not evidence approval.**
- Unknown PackSpec requirement IDs, unknown service bindings, malformed candidate data, unauthorized OIDC roles and cross-service requests fail closed.

**This is a source-candidate governance gate, not an end-to-end business-answer evaluator.** It does not invoke the general evidence event ingest API, attach signed custody to Drive text, resolve semantic support, or make an `ADMIT` assertion. Other applications may still use the generic evidence intake and must separately integrate the same controls before claiming that exclusion is universal. The check is transient and is not itself an externally anchored telemetry record.

Run a **real local HTTP demonstration using synthetic Drive files and mock identities**:

```sh
npm --prefix apps/registry install
npm --prefix apps/registry run drive:governed-demo
```

It shows `INCONCLUSIVE` for an included-but-unreviewed source, `REFUSE` after owner exclusion (even after resync), `INCONCLUSIVE` after explicit re-inclusion, and `INCONCLUSIVE` after index deletion.

### Protected service ingress: enforce beyond the Studio preview

The per-source Drive check is **not** enough on its own: an authorized
downstream application could previously bypass the owner’s exclusion by
submitting synthetic source-origin metadata directly to the generic registry
evidence endpoint.

For a specifically configured `serviceId@environment`, the new
`BLOCK_UNATTESTED_GENERIC_EVIDENCE` mode now **fails closed** on
`POST /v1/evidence/evaluations`. No client-supplied `src_` or `org_`
token, request ID, override flag or unverified citation can reach the
metadata evaluator and obtain `ADMIT` for that protected scope.

Customers with signed `evidence.reader` permission and scope can see the
configured mode, observed ingress denials, pinned PackSpec and unresolved
safety boundaries in **Recorded Evidence Assurance**. A locally
hash-chained, metadata-only protection activation record prevents silent
configuration downgrade when the same ledger is reused on restart.

**What is not yet controlled:** alternate registries, independent model
inference endpoints, external SDK consumers and historical admissions
recorded before protection. The protected service's generic path
intentionally blocks even legitimate generic submissions. A
**separate, opt-in human-signed admission endpoint** now exists:
`POST /v1/evidence/protected-admit` verifies two customer role signatures,
the currently pinned registry PackSpec, live Google source bytes and owner
controls, then records an `ADMIT`, `REFUSE` or `INCONCLUSIVE` decision
with an independently replayable receipt. `ADMIT` denotes a **human-signed,
scoped assertion**, not independently proven source truth. Only
single-origin/no-publication-freshness PackSpecs are supported in this
research bridge; unsupported policies fail closed. The
`governed-check` route itself remains an **INCONCLUSIVE/REFUSE-only**
candidate review.

[Protected Drive ingress — setup and runnable proof](PROTECTED-DRIVE-INGRESS.md)

### Observe a candidate vs record a reviewer challenge

A normal `POST /v1/drives/google/governed-check` is non-mutating and
does **not** create ledger telemetry. Users can preview a source control
result without writing an audit event. An explicit
`POST /v1/drives/google/record-check` uses the same server-side PackSpec
and index checks but additionally requires `evidence.reviewer` and an
enabled evidence ledger. The check result remains **REFUSE or
INCONCLUSIVE only**; the act of recording is **not** customer acceptance.

Recorded checks appear in Studio's Evidence Assurance counts and carry
a local receipt. The ledger omits document content, source IDs, and
revisions. Each reviewer is limited to 20 recorded checks per rolling
minute. The hash chain is **not externally anchored**.
This makes visibility deliberate without allowing read-only identities
to flood or mutate the evidence ledger.

### A justified narrow admission with independent replay

The new **Customer-signed protected evidence review** panel accepts an
offline package approved by two distinct role keys (source custodian and
semantic reviewer). The registry verifies exact current owner-controlled
Drive bytes before recording a result; the signed package contains digest
metadata rather than raw document text. The resulting receipt can be
independently re-evaluated through the Python verifier with approved public
keys and exact source bytes.

The product must display **which assertions a customer accepted** and
**which facts remain unproved**: a key signature is not original publisher
authentication; distinct keys are not necessarily separate people; and
an approved excerpt can omit hidden constraints. External inference apps
must integrate this protected route before asserting global enforcement.

**[Human signing, verification, and limitations](PROTECTED-HUMAN-REVIEW-ADMISSION.md)**.

### Evidence promotion boundary

`SEARCH_CANDIDATE` → customer inspection of original → separately verified provenance and authority → reviewed PackSpec obligation → evidence-gate evaluation → `ADMIT` / `REFUSE` / `INCONCLUSIVE` → independent replay / customer challenge.

The Drive inclusion toggle **cannot** jump any step in this sequence. A document's location, name, checksum, number of copies, or lexical similarity never establishes independent origin or semantic support.

## Customer acceptance test

A skeptical customer should be able to:

1. View a partial index and identify exactly which file was skipped.
2. Exclude a sensitive source, rerun search, and observe that its passage is no longer retrievable.
3. Resync an updated document and confirm the exclusion is still enforced.
4. Use a different OIDC account and demonstrate that the first account's inventory and settings are inaccessible.
5. Delete the index while a sync is running and verify that the finished sync cannot restore it.
6. Export the **unsigned** visibility report and separately challenge a QualityRAG evidence receipt with the Python verifier and optional customer custody mapping.

The tests cover the simulated provider/runtime workflow, but no real customer's acceptance has been recorded. The next release gate is to prove this in a customer-controlled staging environment with approved test data, then independently review OAuth scope, access revocation, retention and logging.

**Positioning:** The credibility proposition is not “trust our AI”; it is “see the evidence, control the boundaries, challenge the verdict.”
