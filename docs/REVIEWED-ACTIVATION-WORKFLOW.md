# Complete reviewed activation workflow

The activate-plan API connects authenticated source custody, signed release
compatibility, an independently keyed preservation review, the bounded interpreter,
actual output checking and authorized original-source fallback in one operation.
It reuses the existing PackSpec compiler, unified finite gate and signature code.

## Run complete examples

~~~bash
python -m tools.activation_runtime.worked_workflows --out /tmp/reviewed-workflows
~~~

This creates four separately compiled, source-anchored domain PackSpecs and twelve
worked paths: preserved, refused and fallback for clinical-description, nursing,
legal and education inputs. Each path includes the complete request, signed
manifest/review, contract and actual receipt with execution trace. The aggregate
receipt records hashes and relative receipt paths. The negative cases inject an
unsupported diagnosis, remove NOT/change units, reverse legal roles/polarity or
change an educational exception. Refusals expose no output. Fallback reconstructs
the signed original under the same reviewed obligations.

These are authored examples. Their fresh, separately generated author/reviewer
keys exercise cryptographic separation; they do not represent real independent
domain reviewers. Private keys and bearer tokens are not exported. The execution
clock is pinned to the fixture signature period for reproducibility. Re-running
requires a fresh output directory and creates fresh signatures; exported consumed
approvals are not reusable production requests. The existing run_research command
separately reconstructs actual authored audiovisual files and retains its negative
AV1 comparison. No real clinical/legal validity or compression advantage is claimed.

## Host configuration

The serve command accepts an optional preservation object in its existing public
key configuration. It is keyed by authenticated tenant:

~~~json
{
  "preservation": {
    "your-tenant": {
      "review": {"reviewer-key-id": "BASE64_ED25519_PUBLIC_KEY"},
      "subjects": {"reviewer-key-id": "reviewer-subject"},
      "authors": {"contract-author-subject": "BASE64_ED25519_PUBLIC_KEY"}
    }
  }
}
~~~

This supplements the existing access, release and minimum_sequence configuration.
The host controls these public-key/subject mappings; clients cannot supply them.
Tenants without configured preservation authority cannot use activate-plan.
The application clock, release trust/revocation and version floor are host owned.
The host must authenticate real reviewer identities and competence separately.

## External request and clients

Upload the exact source and canonical finite artifact through the existing source
API. The signed release must pin both objects and the external policy IR. Draft
and independently sign the preservation contract context described in
PRESERVATION-OMISSION-AUTHORITY.md. The request contains exactly:

| Property | Meaning |
|---|---|
| source_sha256 | Immutable source object in the authenticated tenant |
| artifact | Total finite field mapping and actual candidate payload |
| signed_manifest | Trusted release signature over the exact source/artifact/policy |
| policy_ir | External checked PackSpec ConstraintIR |
| contract | Source-anchored preservation obligations and designated author/reviewer |
| signed_review | One-time PRESERVATION_CONTRACT_REVIEW approval |
| allow_fallback | Explicit boolean permitting the same signed original as fallback |

~~~python
receipt = client.activate_plan(**request)
~~~

~~~typescript
const receipt = await client.activatePlan(request);
~~~

~~~bash
python -m tools.activation_runtime.cli activate-plan \
  --endpoint http://127.0.0.1:8769 \
  --token /path/to/access-token.json \
  --request /path/to/reviewed-request.json
~~~

The HTTP endpoint is POST /api/activate-plan. It requires an authenticated read
principal, tenant-scoped custody, configured author and reviewer public keys, a
valid release and an independent preservation review. Request tenant/time/key
options are rejected. The response includes the actual interpreter trace, candidate
omission audit, canonical finite/unified gate result, signed-review binding and
release compatibility. It grants no automatic domain admission or generation.

## Outcomes and fallback boundary

| action | Behavior |
|---|---|
| REQUIRES_REVIEW | Finite exact checks pass; preserved output is returned; domain admission remains INCONCLUSIVE |
| REFUSE | Candidate fails and fallback is disabled; output is null |
| FALLBACK | Candidate fails; the original from the same signed, authorized custody is independently checked and returned |

A successful candidate never unnecessarily invokes fallback. A failed candidate
can invoke it at most once. The fallback inherits no assumed fidelity: the actual
original is rechecked against the current contract/IR. Missing/corrupt source or
artifact, incompatible/revoked/expired release, invalid reviewer identity or stale
contract refuses the operation. Fallback does not bypass these failures. There is
no arbitrary alternate URL, decoder plugin or client-supplied fallback callback.

The workflow is the bounded exact flat-JSON runtime. The separate omission/audit
API supports declared numeric approximation, but a permissive tolerance cannot
bypass canonical exact-runtime refusal here. Image/PDF parsing, learned semantic
transformation and video playback are separate supported research paths, not
implicitly enabled by this endpoint. Source and artifact remain in immutable
custody; successful review nonces persist across application restart. The review
is one-time, and the caller should retain its receipt; a lost response requires
fresh review rather than replaying the consumed authorization.

## Verification

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p test_reviewed_workflow.py -v
~~~

Real HTTP tests cover all three outcomes across Python, TypeScript and CLI;
four domain flows; cross-tenant access; persisted replay refusal after restart;
source/policy/contract corruption; key revocation; missing authority/custody;
subject mismatches; strict options and the exact-runtime boundary. CI also runs
all twelve worked examples and uploads their inputs and receipts.

For source-file staging and the browser workspace, see REVIEW-WORKSPACE-WORKFLOWS.md. The optional CLI --source argument uses the same staged path.
