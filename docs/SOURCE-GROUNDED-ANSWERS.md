# Source-grounded answers — exact extracts, not imagined entailment

**Status:** Research pilot on draft PR #85, unmerged and undeployed.

## The problem we are testing

A verified source document does **not** guarantee that an AI-generated
answer preserves its exceptions or constraints. Nor does seeing an
exception phrase in an answer prove the phrase was interpreted correctly.

To avoid inventing semantic certainty, QualityRAG now supports a
**strictly extractive output mode**. The registry, not the generative
model, constructs the response from exact, current, customer-signed
source lines. This is *byte-anchored output*, not natural-language
entailment testing.

## Protected operation

`POST /v1/evidence/protected-decisions/{decisionId}/grounded-deliver`

A source-owner OIDC principal needs `evidence.ingest`,
`drive.reader`, signed service scope, a protected service,
a currently approved PackSpec and an unrevoked, two-role-signed
`ADMIT` decision.

The **only** accepted request fields are:

```json
{"requestId":"unique-grounded-response-001"}
```

No caller-provided answer, arbitrary excerpt selector, prompt, or
claimed source revision is accepted. The server:

1. Revalidates the existing two trusted custodian/meaning-reviewer
   signatures and current approved PackSpec.
2. Re-downloads all signed witnesses' exact original Google bytes
   from the owner's currently selected, authorized folder.
3. Checks exact full-file and source-line SHA-256, current exclusions,
   selected folder, source index freshness, and owner permissions
   after provider I/O.
4. Requires **every PackSpec requirement** to have at least one
   human-signed `SUPPORTS` witness. A `CONTRADICTS` or `UNKNOWN`
   witness, missing requirement, invented anchor, changed line, or
   unsupported multi-origin/publication-freshness obligation blocks
   extraction.
5. Renders **all signed SUPPORTS anchors** in deterministic PackSpec
   requirement order, with their exact text and source/line identifier.
   Includes the one immediately preceding/following line, where
   present, explicitly labeled **unreviewed adjacent context**.
6. Appends an explicit warning about other, unseen exceptions,
   conditions and contradictions elsewhere in the document.
7. Records only a digest and authorization metadata in the local
   ledger, tagged `SOURCE_GROUNDED_EXTRACT`, then returns the
   extract and a receipt tied to its exact SHA-256.

A single document can contain a distant exception outside the
one-line context window. That exception **will not be discovered**
merely because the response is extractive. The reviewer must sign
appropriate witnesses for every material condition, or the system
must use a separate full-document sufficiency and contradiction
analysis. These remain explicit release blockers for unrestricted
free-form output claims.

## Example: what is and is not proven

Synthetic input:

```text
Line 1: Reimbursement requires prior approval.
Line 2: Except emergencies, which must be reported within 24 hours.
```

If both lines are human-reviewed `SUPPORTS` witnesses bound to
distinct PackSpec obligations, the deterministic extract contains
both lines **verbatim** and their source anchors.

If the reviewer signs only line 1, the adjacent line 2 is still
displayed as **unreviewed context**, but the system cannot assert
that all exceptions were captured. If the policy has an explicit
`exception` requirement and no corresponding signed witness,
the extract is **refused**.

The response makes these distinctions machine-readable:

```json
{
  "schema": "qualityrag.source-grounded-extract/v1",
  "coverage": {
    "allSignedAnchorsIncluded": true,
    "adjacentContextWindowLines": 1,
    "fullDocumentExaminedForExceptions": false
  },
  "assertions": {
    "exactLinesRevalidated": true,
    "humanReviewedAnchorSemantics": true,
    "modelGeneratedParaphrase": false,
    "freeFormAnswerEntailmentVerified": false,
    "documentWideCompletenessVerified": false,
    "independentPublisherVerified": false
  }
}
```

This is an illustrative subset of the response, not an
independently audited customer result.

## Studio and SDK

Studio's **Generate exact-source extract** button appears for
customer-approved protected decisions. The output is shown with
required-obligation coverage, adjacent context, and explicit
unresolved completeness warnings. It does not require the user
to paste a model-generated answer or provide an arbitrary excerpt.

TypeScript applications can call:

```ts
const extracted = await guard.extractFromReviewedSources(
  signedDecisionId,
  uniqueRequestId
);

// Only the server-generated exact extract is returned.
// Do not replace it with unrelated model prose.
return extracted.answer;
```

The SDK checks the result schema, complete signed-anchor coverage,
limited assurance flags, digest-bound receipt, and delivery mode.
The registry receives/returns exact protected source text; deploy
only within a customer-controlled trust boundary. The ledger never
intentionally stores the extracted passage.

## Acceptance and adversarial validation

Run the existing registry and TypeScript suites:

```sh
npm --prefix apps/registry install
npm --prefix apps/registry test
npm --prefix sdk/typescript install
npm --prefix sdk/typescript test
```

Tests include:
- Required approved line **and exception** both appear unchanged
- A required exception not signed -> **refuse**
- Contradicted/unknown review status -> **refuse**
- Changed hash, missing/duplicate/invented anchor -> **refuse**
- Oversized quote -> **refuse rather than silently truncate**
- Owner exclusion, policy change, decision revocation or replay -> **refuse**
- Denied response contains no protected document text
- Local ledger records the extract digest/mode, not the passage

## Unresolved scientific and operational questions

- A signed reviewer can mistakenly approve an incomplete set of
  witnesses. This system does not automatically find all unknown
  unknowns, deceptive witnesses, distant conditions or ambiguities.
- Exact extraction preserves surface text and prevents unsourced
  paraphrase, **not the meaning of a generated answer**.
- All original source constraints still require proper semantic
  witness discovery, cross-source conflict checks, trust provenance,
  and human review; broader support is future work.
- The local hash-chained ledger, scoped OIDC and selected-folder
  Drive prototype are not a production, multi-tenant certified
  evidence system.
- External applications can bypass any registry gateway unless
  output architecture and routing prohibit it.

**Customer-facing proof statement:**
“We can show exactly which customer-reviewed source clauses were
released, which required obligations they covered, and which
completeness questions remain unresolved.” No stronger claim.
