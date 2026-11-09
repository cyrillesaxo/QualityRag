# Dodo Apply — safety-first Chrome extension prototype

This is an **unreleased prototype**, not a functional QualityRAG/LexyRead integration. It provides a small, user-initiated contact-field autofill capability for evaluation against real ATS forms. It deliberately does **not** auto-submit or answer screening questions.

## Load locally

1. Open `chrome://extensions` and enable Developer mode.
2. Click Load unpacked and select this directory.
3. Open a job application page, click the extension, enter only verified contact fields in JSON, and click Save locally, then Fill contact fields.
4. Review changes; submit manually.

## Security boundaries

- No server calls or background uploads; contact profile resides in `chrome.storage.local`.
- No broad host permission; `activeTab` permission follows a user action.
- Only known, unambiguous empty contact fields are filled; sensitive questions, employment dates, eligibility, salary, and free-text answers are never inferred.
- No attempt to defeat ATS restrictions or CAPTCHAs.
- This prototype is not ready for public distribution. Before publishing: add an explicit privacy notice, threat model, permission review, accessibility testing, and tests on real ATS forms.

## Backend integration design (not yet implemented)

**LexyRead:** Interpret a screening question into structured obligations: requested fact, scope, temporal range, negation, exceptions, and ambiguity. Never derive facts from interpretation alone.

**QualityRAG:** Check the candidate answer against a user-approved profile and source references under a versioned application PackSpec. Use verdicts ADMIT / REFUSE / INCONCLUSIVE. Inconclusive or refused answers remain blank and require human review. An ADMIT verdict is evidence-contract satisfaction, not truth or legal eligibility.

Proposed integration request: `{question,fieldContext,candidateAnswer,profileRefs,packId,consent}`; response: `{verdict,reasonCodes,evidenceRefs,needsReview}`. Implement an authenticated backend proxy; never ship service tokens in extension code. Record user consent and minimize PII retention.

## Next validation gates

- Automated DOM fixture tests for contact-field matching and non-matching fields.
- React-controlled inputs, iframes, dynamically rendered forms and Workday acceptance tests.
- Data-provenance and negative screening-question test corpus.
- LexyRead question interpreter and QualityRAG SDK adapter, independently tested.
- User-controlled review/approval, then an application tracker.
