# Constraint-signal sufficiency preflight — bounded and fail-closed

**Status:** Experimental, draft PR #85, not merged or deployed.

## Why this matters

An approved witness for “prior authorization is required” does not
establish that there is no exception twenty paragraphs later.
A one-line neighbor preview is insufficient to discover distant
conditions. QualityRAG must not confuse **extraction completeness
over reviewed anchors** with **semantic completeness of the source**.

This pilot adds a deterministic **review-candidate scanner** over
**every indexed line of each exact live-verified *referenced* file**,
rather than only the anchor and its neighbors.

## What the scanner detects

Current bounded English-language patterns include:

| Category | Example markers |
| --- | --- |
| EXCEPTION | except, excluding, other than |
| CONDITIONAL | unless, only if, provided that, subject to |
| OVERRIDE | notwithstanding, however, despite |
| NEGATION | must not, may not, does not apply, shall not |

These are lexical indicators, **not proven semantic relations**.
A harmless use of “however” can be flagged, and a logically
important distinction without any of these expressions can be
missed. There is no claim of recall, entailment, or contradiction
detection across arbitrary paraphrases.

A line is considered *already reviewed for this limited purpose*
only if it is present in the same signed human-review payload
as a `SUPPORTS` witness. `UNKNOWN` and `CONTRADICTS` status
never silently clear a candidate.

## Customer preflight endpoint

`POST /v1/evidence/protected-decisions/{id}/sufficiency-check`

Requires the same OIDC owner, `evidence.ingest`, `drive.reader`,
protected service/environment scope, signed reviews, current PackSpec,
live Google Drive access, original file bytes and active source
permissions as the extractive gateway.

The bounded request accepts only a unique-style `requestId`:

```json
{"requestId":"inspect-constraints-001"}
```

The response contains a candidate **count**, opaque source ID,
line number and rule category. It deliberately contains **no source
passages**. The user can inspect the document using the existing
private Drive inventory and agree on a new separately signed review.

Example **illustrative** outcome (IDs shortened here):

```text
status: UNREVIEWED_LEXICAL_SIGNALS
candidateCount: 1
source: google_drive/<opaque>, line: 19, category: EXCEPTION
releasePermittedByThisPreview: false
documentWideSemanticCompletenessVerified: false
```

The actual machine-readable source ID is always the full opaque
32-hex digest, not the shortened placeholder shown in this explanation.
The preflight **does not** append a review event or return a release
permit, avoiding an audit ledger mutation for ordinary inspection.

## Release boundary

`grounded-deliver` always runs this scan after the existing
live-byte and owner-control rechecks.

- If there is **any unreviewed signal**, refuse extraction with
  `PROTECTED_SUFFICIENCY_UNREVIEWED_SIGNAL`, HTTP 409.
- Store one **metadata-only** `constraint-block` record with
  service/environment, owner hash, policy digest, decision ID,
  hashed request identifier, candidate count and fixed reason.
  Raw line text and opaque source IDs are not copied to this ledger
  event. Reviewer-flood limits apply.
- If the referenced file scan is incomplete or malformed, refuse.
- If no lexical signal is found, other existing checks and the
  exact-source extraction builder still apply. The builder requires
  an explicit trusted zero-candidate scan instead of assuming one.

Studio shows the candidate source ID, line and category and a
distinct **observed sufficiency-block counter**. A clean scan
is never labeled “semantically sufficient.”

## How a customer resolves a flagged clause

1. Run `sufficiency-check` in Studio, record the opaque source ID,
   line number and category. Inspect the exact original source
   through the owner's configured Drive folder.
2. Determine whether the signal is actually a relevant exception,
   condition, contradiction, or harmless wording. Lexical matching
   alone cannot decide.
3. If relevant, make sure the **approved PackSpec** represents the
   requirement or exception; changing only witness metadata cannot
   introduce an approved policy obligation.
4. Build a **multi-witness offline review manifest** containing both
   the main clause and relevant exception, with explicit status,
   requirement mapping and exact local original-file path.
5. The separate source custodian and meaning reviewer sign the
   same newly prepared payload. Studio submits it as a **new
   signed decision**.
6. Rerun `sufficiency-check`; if the detected line has a reviewed
   `SUPPORTS` witness, that candidate is no longer unreviewed.
   `grounded-deliver` still performs a fresh live-byte, scope,
   PackSpec, and source-control check before releasing any extract.

See [multi-clause preparation and offline signing](PROTECTED-HUMAN-REVIEW-ADMISSION.md).
Passing this workflow does **not** prove that all implicit or
unreferenced constraints have been found.

## Synthetic adversarial challenge

Consider a signed witness for line 1:

```text
Line 1: Prior approval is required.
Line 2: Ordinary billing administration.
...
Line 19: Except emergency cases, which must be reported within 24 hours.
```

Two distinct approved reviewer keys can sign line 1, and the
original source bytes can still match perfectly. The current scanner
flags the unreviewed *line 19*, and the extractive gateway refuses
release. The source owner must examine the exception and explicitly
record an appropriate review in a new signed decision.

Negative cases retained as regression evidence:

- Swapping **payer and payee** without any lexical marker may
  produce zero candidate signals. This scan cannot detect that.
- An exception in a **different unreferenced file** is outside
  the scan scope.
- “Except” in a harmless example can generate a false alarm.
- A human signer may approve an inaccurate interpretation or attach
  an exception to the wrong PackSpec obligation.
- Some expressions cross paragraphs and are not interpretable from
  lexical marker location alone.

Therefore the output keeps
`documentWideSemanticCompletenessVerified=false` and
`wholeFolderScanned=false` even after a clean scan.

## Verification

```sh
npm --prefix apps/registry install
npm --prefix apps/registry test
npm --prefix apps/registry run admission:demo
```

The unit tests cover distant exceptions, unsigned conditions,
reviewed vs unknown statuses, duplicate/incomplete source inventories,
bounded candidate lists, no source-text echo, and the deliberate
payer/payee blind spot. HTTP integration tests cover valid dual
signatures with a distant, unsigned exception and demonstrate
fail-closed extractive release.

**Customer promise:** We show the exact reason a reviewed-source
extract was blocked and let the customer decide what needs
investigation. We do **not** assert that every missing constraint
has been discovered.
