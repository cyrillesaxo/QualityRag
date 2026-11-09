# Cross-document relationship challenge — candidate WitnessGraph v0.1

**Experimental research pilot; PR #85 remains draft, unmerged and undeployed.**

## The gap beyond lexical exception detection

A signed claim that "the insurer must pay the hospital" can be
contradicted by a different document stating "the hospital must pay
the insurer." Neither sentence necessarily contains `except`,
`unless`, or another explicit exception marker. The prior
file-wide lexical preflight can therefore miss the relationship
change.

QualityRAG now implements a **narrow, deterministic cross-source
relation candidate graph**. It examines the customer's **included**
text files in the **selected Google Drive folder**, not the entire
Drive account or all external sources.

### What the implemented grammar can parse

Current full-line English forms:

- "The insurer must pay the hospital."
- "The hospital pays the insurer."
- "The insurer shall not pay the hospital."
- "The hospital does not pay the insurer."

The parser recognizes single-token actor labels and `must pay`,
`shall pay`, `pays`, `must not pay`, `shall not pay`, or
`does not pay`. It normalizes case and detects two categories
when the matching assertions are from **different files**:

| Candidate | Example |
| --- | --- |
| `INVERSE_PAYER_PAYEE` | A pays B versus B pays A |
| `POLARITY_CONFLICT` | A must pay B versus A must not pay B |

Neither category is a *proven contradiction*. Both directions can
sometimes be true for different transactions, jurisdictions, time
windows or legal capacities. And distinct signers approving both
statements **does not decide which applies**.

Complex grammar, aliases, organization hierarchies, implicit roles,
speaker intentions, temporal scope and jurisdiction are not solved.
The detector deliberately preserves examples it cannot recognize
as known negative results instead of claiming complete coverage.

## Proof and privacy boundary

The existing protected source-owner and signer checks run before a
relation preview or grounded release:

1. Validate OIDC `evidence.ingest` and `drive.reader`, signed
   service scope, current PackSpec and dual reviewer signatures.
2. Require the selected-folder index to report complete supported
   text coverage and be recent. Explicitly excluded files are **not
   included**; this limitation is shown to the customer.
3. Re-download the exact original bytes of **every currently
   included indexed text file** in that folder using the customer's
   active Google authorization. Verify each digest against the
   encrypted index, under a bounded maximum of 40 files, 96 KiB/file
   and 1.5 MB indexed total.
4. Check current account, folder, original file bytes, active sync
   and inclusion settings **again after Google I/O**.
5. Apply the bounded deterministic relation grammar and compute
   candidate cross-file edges. The response contains **only**
   opaque source IDs, line numbers, categories and counters.
   No names, textual clauses, original filenames or LLM drafts
   are included in the preview or metadata-only block ledger.

These are bounded guarantees **only for the current selected-folder
scope**. A user can explicitly exclude a file, making it no longer
eligible for detection; that is customer control, **not evidence that
the excluded source is false**.

## Preview endpoint

`POST /v1/evidence/protected-decisions/{id}/relation-check`

Only one request field is accepted:

```json
{"requestId":"check-payer-payee-0001"}
```

Example response shape (illustrative, not real customer data):

```text
status: POTENTIAL_CROSS_SOURCE_CONFLICTS
sourcesScanned: 2
candidateCount: 1
bothSignedConflicts: 0
finding:
  category: INVERSE_PAYER_PAYEE
  left:  source google_drive/<opaque>, line 3, signed witness yes
  right: source google_drive/<opaque>, line 1, signed witness no
releasePermittedByThisPreview: false
semanticCompletenessVerified: false
```

The actual response uses the full machine-readable opaque source
IDs and marks each edge with its exact line. No source text is
emitted. A clean result means only **no supported-pattern conflicts
found**. It is not proof of semantic consistency.

## Fail-closed grounded extraction

The `grounded-deliver` endpoint always performs the same
**fresh** cross-source scan after exact live provider verification
and before any output is returned.

If any candidate remains, it refuses with
`PROTECTED_GROUNDED_CROSS_SOURCE_RELATION_CONFLICT` (HTTP 409).
A separate metadata-only `relation-block` record stores the
fixed reason, decision/policy/owner hashes, event time and candidate
count. **Neither signing both conflicting claims nor merely
rerunning the check clears it.**

The customer must investigate source authority, dates, applicable
transaction, legal scope and the correct mapping of payer and
payee. A new signed PackSpec interpretation, source correction,
or explicit out-of-scope exclusion may change the applicable
evidence. No automatic truth or precedence adjudication is
implemented, and exclusions must remain visible to the owner.
The system does not automatically promote a different source
to authoritative status.

Studio shows candidate pairs and signed witness flags, then leaves
resolution under owner control. The TypeScript SDK exposes
`checkCrossDocumentRelations()` and refuses overstated
completeness, leaked actor names and malformed scope metadata.

## Reproduce and challenge

```sh
npm --prefix apps/registry install
npm --prefix apps/registry test
npm --prefix apps/registry run admission:demo
npm --prefix sdk/typescript install
npm --prefix sdk/typescript test
```

The tests demonstrate:
- Two files with opposite payer/payee roles cause a candidate,
  even with no exception keyword.
- A positive and negative obligation on the same directed edge
  produces a distinct candidate category.
- **Both statements may be signed SUPPORTS and still remain
  unresolved.**
- Changes to another selected file's bytes fail live verification.
- Excluding another file **while Google is reading** invalidates
  the scan, then the next scoped check reflects that exclusion.
- A metadata preview does not release content; blocked extracts
  create only bounded audit metadata.
- Unsupported "transfers funds to" paraphrases produce no finding;
  `semanticCompletenessVerified=false` remains explicit.
- Oversized graphs refuse rather than truncate away unseen
  conflicting edges. The candidate list may be truncated, but
  the full candidate count still blocks output.

## Future FF-RCT / semantic grammar research

A broader model must represent **entity attributes, role slots,
relation direction, negation, applicable date, authority, scope,
and semantic witness links**. The next experiment should evaluate
graph-relationship transfer across multiple domains with
adversarial, cross-lingual and implicit-relation examples.
Promote a grammar change only when independent tests establish
better consequential-change recall without an unacceptable
false-block rate. The present implementation is **one constrained
pattern family**, not validated FF-RCT semantic transfer.

**Commercially credible statement:**
“We can show a customer an exact source pair whose explicit payer/payee
roles appear inverted, block the source-grounded extract, and let the
customer verify and control the resolution. We cannot yet guarantee
finding all semantic conflicts.”
