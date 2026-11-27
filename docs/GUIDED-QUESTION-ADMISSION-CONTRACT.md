# Guided question admission contract — proposal v0.1

Status: proposed integration contract; no production endpoint, reviewer enrollment, or semantic verification is implemented by this document.

## Scope

FF-RCT PackSpec v2.1 GQDC/SQC. A learner's selected concept and goal identify an investigation, not a diagnosis. Reuse the registry's existing authenticated review and source-custody patterns; do not call its Drive-specific protected-admit endpoint for arbitrary transcripts or local documents. Metadata replay is not semantic proof.

## Review request

Bind tenant/owner, service/environment, policy version and digest, source ID and revision, semantic concept ID and revision, goal ID, evidence ID and obligation ID, exact source span and quote, operator and semantic kind, typed argument roles and exact spans, relation ID/direction where present, and the proposed premise. An independent authorized reviewer must evaluate relevance, premise, semantic roles, source scope, material consequence and unresolved alternatives. Missing or contradictory evidence must not be upgraded by a template or source match. Canonical serialization and digest/signature rules require a versioned implementation and cross-language fixtures before release. Do not trust hashes supplied by the learner.

## Verdicts

- ADMIT: authenticated, current, scoped human-reviewed assertion; not machine-certified truth. The server may translate this to a LexyRead SAT review receipt only after independently verifying identity, signature, content binding, policy and revocation.
- REFUSE: reject the premise or target; preserve the reason code; do not surface it as a recommended question.
- INCONCLUSIVE: retain an explicitly unreviewed investigation prompt when safe; otherwise abstain.
- Answer status and learner mastery remain independently UNKNOWN unless their respective evidence requirements are satisfied.

## LexyRead boundary

Existing buildGuidedQuestionLens(reviewEvidence) is a synchronous host callback, not a network authority. The existing questionTargetBinding serializes source, concept, goal, evidence, obligation, kind, span and typed arguments. It is a content identifier, not a signature or full authority envelope. The host must resolve a verified receipt server-side; no browser-held signing key and no caller-generated SAT. Missing or mismatched target binding may fall back to source-context wording only if base premise review independently remains valid. Refused premise must not be bypassed by fallback.

## Acceptance gates

1. Scope and revision mutations, role substitutions, direction reversal, quote/offset changes, wrong policy, wrong tenant, expired/revoked reviewer, replay across scope, unavailable authority and false premise must fail closed.
2. Metadata-only ADMIT cannot create semantic review authority.
3. Typed target mismatch cannot retain typed wording.
4. Unreviewed proposals remain separate from reviewed recommendations.
5. No automatic export of private source content or learner events; use explicit authorized server-side retrieval and retention limits.
6. Establish cross-repository integration tests and an independently reviewed positive fixture before merge/deploy.

## Non-goals

No new service or production credentials, no general-purpose semantic proof, no claim of WBC optimality or verified learner mastery. Existing Drive-specific and metadata gates remain unchanged.
