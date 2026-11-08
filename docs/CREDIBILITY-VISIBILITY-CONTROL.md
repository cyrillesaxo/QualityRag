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
