# QualityRAG Studio — Customer-Controlled Source Custody Challenge

**Status:** Experimental, local-first evidence assurance. This feature provides an additional **optional, offline customer custodian signature and exact-source-byte check** on exported Studio replay packages. It does not establish real-world source authority, semantic correctness, or independent source authorship.

## Why this matters

The existing independent Python replay verifies that the v0.1 metadata gate computes the same verdict as the JavaScript registry. It can still be fooled when the telemetry producer invents source-origin labels and recomputes a self-consistent receipt.

**Adversarial test:** Three citations with one origin return `INCONCLUSIVE`. A dishonest producer relabels one as a second origin, recomputes the unsigned receipt and gets `ADMIT`. The ordinary independent replay reproduces the forged declaration. The custodian-signed source manifest ties each `src_...` reference to the original reviewed `org_...` claim and exact SHA-256 source bytes, so the relabeling is **rejected**.

## Reuse existing QualityRAG governance primitives

This work deliberately reuses the existing `tools/packspec_compiler/signed_bundles.py` implementation: **QR-CJSON-1** deterministic canonical JSON, the `qualityrag.signed-observations/v1` Ed25519 signature domain, and `sign_attestation` / `verify`. It follows the verified-byte custody principle already explored in [RCT Source Custody v1.9](RCT-SOURCE-CUSTODY-v1.9.md).

The Studio bridge is a **narrower, separate contract** than the full experimental RCT v1.9 custody chain. Its `policy_signature` field is explicitly prefixed `UNSIGNED-V0.1-PACK-SHA256:` and binds a digest of an **unsigned** PackSpec; it does **not** claim that the PackSpec itself has been signed/approved by an independent governance key. The signed observation body is `studio_custody` with the following customer-reviewed claim:

- `evaluationId`, `serviceId`, `environment` and `policySha256`;
- one entry for **every** opaque `source_ref`, with the approved **declared** `origin`, exact original file digest and file byte length.

Private keys never enter Studio or the registry. The evaluator still treats the origin assertion as a statement signed by a configured custodian, not independently established historical provenance.

## Reproduce the adversarial demonstration

Install the existing governance dependency set once:

```sh
python -m pip install -r tools/packspec_compiler/requirements.txt
npm --prefix apps/registry install
python scripts/evidence-custody-show-me.py
```

The script actually runs the local JavaScript registry's HTTP evaluation demo and exports its metadata-only replay package. It then checks three synthetic customer-owned source files using a disposable in-process Ed25519 key.

Expected outcome:

```json
{
  "unmodifiedReceipt": {
    "verdict": "INCONCLUSIVE",
    "sourceCount": 3,
    "declaredOrigins": 1,
    "custodySignatureAndBytesVerified": true
  },
  "forgedOriginReceipt": {
    "unsignedReplay": "ADMIT",
    "unsignedReplayAccepted": true,
    "customerCustodyAccepted": false,
    "rejectionReason": "DECLARED_ORIGIN_MISMATCH"
  }
}
```

The demonstration uses **synthetic files and disposable demonstration keys**, not real customer evidence or real purchaser authorization. The CI job `Studio and Registry` runs the same script with Node and Python dependencies installed.

## Customer-controlled signing workflow

The custodian obtains a portable `qualityrag.evidence-replay/v1` JSON exported by Studio and independently reviews the source inventory and genuine underlying files. Source files must be provided **locally** to the custodian and verifier; they are **not uploaded** to a central QualityRAG server.

1. The customer creates and securely stores an Ed25519 private key with restricted file permissions; the approved public key is distributed to reviewers **out of band**.
2. Independently curate a `qualityrag.studio-source-custody/v1` manifest with the receipt's evaluation ID, scope and policy SHA-256. For every `src_...` reference, include `declared_origin`, `content_sha256` and `content_length` from the exact source file. **Never automatically accept the application's origin labels as fact.**
3. Sign on the customer's machine, supplying each exact source file:

```sh
python tools/packspec_compiler/studio_custody.py sign \
  --receipt evidence-replay.json \
  --manifest customer-reviewed-manifest.json \
  --private-key /customer-secure/custodian-ed25519-private.pem \
  --key-id customer-custodian-1 --nonce custodian-approved-eval-001 \
  --out customer-signed-custody.json \
  --source src_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=/customer/files/policy.pdf \
  --source src_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=/customer/files/approval.pdf
```

4. A separate reviewer independently obtains the approved public key, custody attestation, same source bytes and replay package:

```sh
python tools/packspec_compiler/studio_custody.py verify \
  --receipt evidence-replay.json \
  --attestation customer-signed-custody.json \
  --public-key /reviewer-trust/customer-approved-pubkey.pem \
  --source src_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=/reviewer/files/policy.pdf \
  --source src_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=/reviewer/files/approval.pdf
```

Substitute actual source tokens and verified paths from **the specific receipt**. The examples are not ready-to-run against arbitrary documents. Source size is bounded to 2 MB each; up to 100 sources. The manifest must exactly cover the evidence inventory—no silently omitted or unrelated sources. Identical bytes claimed under different origins are rejected.

## What passing does and does not establish

| Verified | Not established |
|---|---|
| Existing independent Python v0.1 metadata replay matches registry result | Authenticity of original real-world publisher |
| Customer-approved public key verifies the signed exact custody claim | Whether distinct documents have independent intellectual origins |
| Exact supplied source bytes match the signed hash and length | Whether retrieved passages support the AI answer |
| Claims match the source tokens, declared origins and policy digest of this exact receipt | Whether PackSpec identified every governing condition |
| Changed origin labels, changed bytes, omitted sources and wrong custodian keys fail | Regulatory compliance, approval to release data, signed business decisions |

**No persistent replay-nonce guard** exists for this offline Studio custody extension. The signed attestation has a bounded validity window and is attached to one evaluation ID. A signature may be replayed within that window; applications must not treat it as one-time authorization. The customer's trust distribution, key rotation, revocation, source governance and retention remain outside this local demonstrator.

## Commercial acceptance experiment

For a first legitimate customer, agree on **one business question**, a PackSpec authored or approved by the customer, and a separate custodian who can authenticate the specific source files. Let the customer rerun the metadata replay, independently review and sign the source mapping, attempt a falsified-source attack, and document disagreements. Record reviewer time and the degree of independence proven; avoid compressing `signed` into `true`.

Before any production deployment, implement externally trusted source authority, distinct tenant custody and signing, key revocation, durable nonce/ledger anchoring, authorization review and verified policy semantics. Do not advertise this local demonstration as a compliance certificate or proof of source truth.
