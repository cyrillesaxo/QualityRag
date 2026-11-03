# QualityRag Studio — signed policy promotion (local development)

This workflow extends the existing local registry. It does **not** replace the legacy unsigned policy API and does **not** introduce production OIDC, RBAC, tenant isolation, or a production key-management service.

**Research attribution:** Cyrille Eloundou / [APX](https://apx.guide/).

## Trust model

- Signing happens **outside Studio** in a governance-controlled process; the registry and browser never receive the private key.
- Studio maintains a read-only map of trusted Ed25519 **public keys**.
- Each promotion is explicitly **STAGED → APPROVED → PUBLISHED**.
- Only the published bundle is returned to applications from the signed endpoint. Existing unsigned endpoints remain separate.
- The signed bundle is scoped to one service, environment, sequence number and validity period.
- Publishing enforces a monotonically increasing sequence per service/environment; the application additionally enforces its own **durable minimum sequence**.
- Applications MUST cryptographically verify the returned signed policy locally and MUST NOT fall back to \`/v1/resolve\`.

**Limitation:** The local registry uses one shared bearer token for staging, approval and publication. Those are distinct workflow transitions but **not independent identities** or separation of duties. Use OIDC/RBAC and authenticated approval records before production.

## 1. Prepare governance signing key and trust store

Generate an Ed25519 key in a secure signing environment and protect it with a secret manager or HSM. For a local sandbox only:

~~~bash
openssl genpkey -algorithm Ed25519 -out governance-private.pem
chmod 600 governance-private.pem
~~~

Export **only the public SPKI DER bytes** into a local trust-store JSON:

~~~bash
python - <<'PY'
import base64, json
from cryptography.hazmat.primitives import serialization
with open("governance-private.pem", "rb") as file:
    key = serialization.load_pem_private_key(file.read(), password=None)
public = key.public_key().public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)
print(json.dumps({"governance-v1": base64.urlsafe_b64encode(public).decode().rstrip("=")}, indent=2))
PY
~~~

Write that output to a protected file (for example \`/etc/qualityrag/trusted-policy-keys.json\`). This file contains **public keys only**. Never commit the private key. Do not send the private key to the registry.

## 2. Create an approved typed IR

Follow [the compiler workflow](../../tools/packspec_compiler/TYPED-IR.md) to produce a reviewed \`typed-ir.json\`. This IR is derived from source clauses and has limited semantic enforcement; it does not certify completeness of the original APX PackSpec.

## 3. Sign outside Studio

~~~bash
python -m pip install -r tools/packspec_compiler/requirements.txt

python tools/packspec_compiler/studio_sign.py \
  --ir-file typed-ir.json \
  --private-key-pem governance-private.pem \
  --output-file signed-policy.json \
  --key-id governance-v1 \
  --service payments-api \
  --environment dev \
  --sequence 7 \
  --issued-at 2026-11-02T10:00:00Z \
  --expires-at 2026-11-03T10:00:00Z
~~~

**Use future/current validity times** for real runs. The dates above illustrate the format and will expire; the signer refuses an invalid interval.

The signer requires restrictive PEM permissions on POSIX systems and refuses to overwrite a signed output file.

### Encoding compatibility

The Node registry verifies signatures produced by the existing Python QR-CJSON-1 signer only for the **ASCII-only, safe-integer subset**. This is not RFC 8785. Unicode source quotations, floating-point parameters, and cross-language escaping differences are deliberately refused rather than guessed. The CI suite tests real Python→Node signing interoperability.

## 4. Run the local registry

~~~bash
export QUALITYRAG_REGISTRY_TOKEN="<a-development-token>"
export QUALITYRAG_POLICY_KEYS_FILE=/etc/qualityrag/trusted-policy-keys.json
export QUALITYRAG_REGISTRY_FILE=./.qualityrag/registry.json
npm --prefix apps/registry start
~~~

Register the consuming service through Studio or \`POST /v1/services\`. In the Studio panel **Signed policy promotion**, paste the already signed JSON, then select **Stage signed bundle**, **Approve signed version**, and **Publish approved version**.

The equivalent HTTP API is:

~~~bash
curl -X POST http://127.0.0.1:5055/v1/signed/promotions \
  -H "Authorization: Bearer $QUALITYRAG_REGISTRY_TOKEN" \
  -H "Content-Type: application/json" --data-binary @signed-policy.json

curl -X POST http://127.0.0.1:5055/v1/signed/promotions/payments-api/dev/7/approve \
  -H "Authorization: Bearer $QUALITYRAG_REGISTRY_TOKEN"

curl -X POST http://127.0.0.1:5055/v1/signed/promotions/payments-api/dev/7/publish \
  -H "Authorization: Bearer $QUALITYRAG_REGISTRY_TOKEN"

curl http://127.0.0.1:5055/v1/signed/resolve/payments-api/dev \
  -H "Authorization: Bearer $QUALITYRAG_REGISTRY_TOKEN"
~~~

The server verifies the signature when **staging, approving, publishing and resolving**. The signed IR and original signature are preserved unchanged; no server-side re-signing occurs. Expired bundles stop resolving.

## 5. Resolve and verify on the application server

~~~python
from studio_signed_client import guarded_generate_from_studio
from signed_gate import SQLiteNonceStore

result = guarded_generate_from_studio(
    "http://127.0.0.1:5055", registry_token,
    policy_keys=pinned_governance_keys,
    attestor_keys=pinned_evidence_keys,
    service="payments-api",
    environment="dev",
    minimum_sequence=7,
    nonce_accepted=SQLiteNonceStore("/var/lib/qualityrag/nonces.sqlite"),
    signed_observations=evidence_attestation,
    witnesses=verified_witnesses,
    observations=verified_probe_results,
    as_of="2026-11-02T10:05:00Z",
    generator=lambda: chat_client.complete(prompt),
)
~~~

Python imports require \`tools/packspec_compiler\` on the module search path. The \`registry_token\`, key maps, attestation and model client are application-owned values.

The application verifies the signature and scope again with its own pinned keys; it does not trust the registry merely because it returned HTTP 200. Missing policy, invalid signing key, expired policy, stale sequence, incomplete evidence or failed attestation blocks generation.

## Known limits

This is **local single-process registry governance**, not enterprise identity, high-availability distribution or a production PKI. It has no independent approver, key revocation feed, distributed locking, audit-log signatures, active replication, or proof of evidence truth. Node's supported signed JSON profile is more restrictive than Python's. The other nine SDKs do **not** yet natively consume the signed ConstraintIR envelope.

The existing unsigned registry can still serve legacy clients; use a dedicated signed endpoint and a signed-only client where signature enforcement matters. Never downgrade from signed policy resolution to an unsigned PackSpec.
