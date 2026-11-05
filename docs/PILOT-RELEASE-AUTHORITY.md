# Research pilot release authority

A readiness label or passing software test cannot authorize a release. The
release gate requires a separately signed approval from a host-configured reviewer
whose key differs from the proposer's key. This API authorizes a bounded research
pilot; it does not deploy software, authorize production, establish semantic
truth, or grant generation permission.

## Exact candidate and target binding

Prepare a manifest with exactly these fields:

| Field | Required value |
|---|---|
| source_sha256 | Original source digest |
| artifact_sha256 | Encoded artifact digest |
| policy_ir_sha256 | Reviewed policy IR digest |
| grammar_sha256 | Grammar digest |
| model_sha256 | Model digest |
| decoder_sha256 | Decoder implementation digest |
| run_id | Bounded host run identity |
| service | Host-configured target service |
| environment | Host-configured target environment |
| sequence | Integer release version at or above the host floor |

Every digest must be 64 lowercase hexadecimal characters. Unknown manifest fields
and missing fields refuse. The signed approval additionally binds its purpose,
tenant, readiness evidence inventory digest, critical-field failure count,
economic outcome and host minimum_sequence. Changing any bound source, target,
evidence or version policy requires fresh approval.

Use release.approval_context to prepare the exact context for the independent
reviewer's existing authority.review_binding process. The proposing process
must not possess an evaluator private key. Then call:

~~~python
from tools.activation_runtime.release import approval_context, authorize_release

context_to_review = approval_context(
    evidence, critical_field_failures=0,
    total_cost_comparison="MEASURED_NO_CROSSOVER",
    context=manifest, tenant=host_tenant, minimum_sequence=host_version_floor,
)
# Obtain evaluator_signed_authorization through the separate host review process.
result = authorize_release(
    evidence, critical_field_failures=0,
    total_cost_comparison="MEASURED_NO_CROSSOVER", context=manifest,
    signed_review=evaluator_signed_authorization,
    reviewer_keys=reviewer_public_keys, reviewer_subjects=reviewer_key_subjects,
    author_public_key=proposer_public_key, as_of=host_time,
    nonce_store=durable_nonce_store, tenant=host_tenant,
    minimum_sequence=host_version_floor,
)
~~~

The host supplies trust maps, subject assignment, tenant, time, version floor and
the durable replay store. These are not options selected by an agent or uploaded
document. Every reviewer key must have a host-assigned subject; the signed name
must match it. A proposer cannot bypass separation with a second key ID for the
same public key. Wrong scope/identity, untrusted or revoked keys, expired grants
and replay refuse. Invalid approvals do not consume the nonce.

## Evidence and outcome boundaries

All eight required evidence categories remain mandatory. A malformed digest or
incorrect evidence status blocks readiness. Critical-field loss and unknown
economics block without invoking release authorization. Evidence status strings
are supplied assertions until the configured reviewer approves their exact
inventory; syntactically valid hashes alone do not authenticate source truth.

A measured no-crossover result is retained and may be reviewed for a research
pilot; it never becomes a claimed economic advantage. Even successful approval
returns release_scope=RESEARCH_PILOT_ONLY, can_release_production=false and
can_generate=false. Preserve the original signed authorization and approved
context with the host's audit records. Verify actual content-addressed artifacts
and runtime compatibility through the existing signed-artifact pipeline before
any use. This helper does not execute a deployment or substitute for that check.

The prior unbound approval format is intentionally unsupported. Callers now need
the complete manifest, reviewer_subjects and minimum_sequence, then a fresh
signature produced from approval_context. Changing the version floor invalidates
an old approval even if its candidate version remains above the new floor.

## Verification

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_release_authority.py' -v
~~~

The authored tests use real Ed25519 signatures and a durable replay store. They
cover every candidate/target/version binding, receipt changes, missing fields,
invalid hashes, reviewer identity, expiry/revocation, same-key aliases, replay,
critical failures and unknown economics. They do not supply physical-device,
licensing, independent fidelity or production acceptance evidence.
