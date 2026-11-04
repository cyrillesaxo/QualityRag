# Signed preservation and omission reviews

US-006/008 now distinguish reviewing a preservation contract from authorizing an
omission in a particular output. A caller's boolean or reviewer label supplies
neither authority. All results remain finite checks with domain admission
INCONCLUSIVE and can_generate false.

## Contract and output checks

Before auditing or binding a review, the runtime reconstructs the complete
contract from actual source bytes, current checked ConstraintIR and declared
obligations. Schema/version, source and policy hashes, per-field anchors,
unspecified-field inventory and residual defaults must match. Duplicate fields,
stale IR contents, altered anchors, and omission of EXACT or UNKNOWN distinctions
refuse. Flat scalar output is bounded by the finite source parser; nested and
nonfinite values refuse. Empty output is structurally valid but all missing fields
still need authorized omission or remain violations.

Approximate numeric comparisons use exact decimal rational arithmetic, including
large JSON integers. Thus source 0.3, candidate 0.4 and tolerance 0.1 meet the
boundary; 0.4000000000000001 is outside it. Booleans are not approximate numbers.
This interprets supplied JSON values, not real-world measurement uncertainty.
UNKNOWN fields remain reported as unknown even when missing, and require residual
preservation. Fields unspecified by the contract also require preservation.

## Authorizing an exact omission

1. Draft a scope with omission_context(raw, output, contract, current_ir=ir).
2. An independent reviewer signs that context using authority.review_binding.
3. Pass the signed envelope to audit_output as signed_omission_review, along with
   host reviewer_keys, reviewer_subjects, author_public_key, as_of and nonce_store.

The signed purpose is PRESERVATION_OUTPUT_OMISSION. The scope binds tenant,
task, actual source hash, checked policy IR/source hashes, complete contract hash,
exact canonical output hash and the complete sorted missing-field set. A changed
retained value, different missing field or changed contract requires fresh review.
Only fields explicitly marked omission_permitted may be omitted; other output
violations refuse before a valid review nonce is consumed. A signature cannot
turn an otherwise invalid candidate into a successful audit.

The host maps each trusted key ID to a subject. That subject must match both the
signed reviewer and the contract's designated reviewer. The author cannot approve
under a different key alias. Existing signature expiry/revocation checks apply.
A durable SQLiteNonceStore reserves each successful review once within the tenant;
reuse refuses. Failed scope, identity, candidate and signature checks do not
consume the valid approval. The host should retain the returned audit as its
receipt. This function does not create a transactional durable audit ledger or
recover a lost successful response; a consumed approval needs a fresh review for
another audit.

Unsigned otherwise-permitted omissions produce UNSAT, residual_required entries
and no approved omitted entries. Successful omissions report the checked reviewer
in omission_review. A signed review supplied when no omission is eligible refuses.
No review grants general permission to omit future outputs or establishes domain
truth, licensing, reviewer competence or source completeness.

## Migration

- omission_reviewed=True and other non-False values now raise PermissionError.
  Keep the default False for ordinary audits; use a signed review for omissions.
- bind_reviewed_contract now requires the host reviewer_subjects map and a
  PRESERVATION_CONTRACT_REVIEW purpose in its signed context. Regenerate older
  unscoped review envelopes instead of reusing them.
- Contract review alone never authorizes a later output omission. The two purposes
  and context shapes differ; using the wrong review does not consume its nonce.
- The interpreter's default audits continue preserving every required field and
  cannot automatically request or manufacture an omission review.

## Verification

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_omission_authority.py' -v
~~~

Tests cover one-time approval, changed outputs, omitted-field sets, host subject
maps, reviewer/author aliases, expired/revoked/rejected signatures, purpose
separation, contract/IR tampering, unknown residuals and exact decimal boundaries.
Actual authorized domain reviewers and independent omission evidence remain
acceptance requirements.
