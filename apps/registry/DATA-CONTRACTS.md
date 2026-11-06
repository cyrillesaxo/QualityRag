# Data contracts in the registry (ADR-0002)

A data contract is a resource's own signed declaration of how its data is classified and where it may go. The registry distributes contracts alongside PackSpecs. The runtime re-verifies every contract it loads, so the registry is a distribution point, never the only check. See [ADR-0002](../../docs/ADR-0002-contract-governed-information-flow.md).

- **Source contract:**
  - every field is either public, or sensitive (it becomes an opaque token); anything else is quarantined;
  - whether free text is owner-classified;
  - which derived attributes may be shown, such as card brand or last four;
  - where data may be released, for which purpose and operation;
  - who may ever see a protected value in clear. That last list can never be broader than the release rules.
- **Destination contract:**
  - which sources, data classes and operations a channel accepts;
  - allowed link hosts and a size limit;
  - when a signed independent review is required.

## Lifecycle

The flow matches signed PackSpec promotion. The registry holds **no signing keys**.

1. **Sign offline** with the contract governor's key:
   ```sh
   python -m tools.activation_runtime.cli contract-keygen --out ~/governor --key-id governor
   python -m tools.activation_runtime.cli contract-sign --contract billing.contract.json \
     --key ~/governor/governor.key --key-id governor --sequence 1 > billing.signed.json
   ```
   `contract-keygen` writes `governor.registry-trust.json`. Point `QUALITYRAG_CONTRACT_KEYS_FILE` at it.
2. **Stage:** `POST /v1/contracts/signed` with the envelope. Needs the `policy.author` role. The registry checks the signature, the validity window (at most 30 days) and the schema.
3. **Approve:** `POST /v1/contracts/signed/{id}/{sequence}/approve` (`policy.approver`, a different person from the author).
4. **Publish:** `POST /v1/contracts/signed/{id}/{sequence}/publish` (`policy.publisher`, different from both).
5. **Resolve:**
   - `GET /v1/contracts/published?tenant={tenant}` returns every published contract for a tenant;
   - `GET /v1/contracts/resolve/{id}` returns one contract.

   Both need `policy.reader`.

`POST /v1/contracts/validate` checks an unsigned draft without changing anything; Studio uses it.

## Guarantees and refusals

| Refused | Code |
|---|---|
| Unknown signing key, or a bad signature | `UNTRUSTED_CONTRACT_KEY`, `CONTRACT_SIGNATURE_INVALID` |
| Expired or future window, or one longer than 30 days | `CONTRACT_EXPIRED_OR_FUTURE`, `INVALID_CONTRACT_WINDOW` |
| A sequence at or below the published one | `SIGNED_SEQUENCE_ROLLBACK` |
| A new version that changes tenant or kind | `CONTRACT_IDENTITY_CHANGE_FORBIDDEN` |
| Detokenization broader than release | `DETOKENIZE_BROADER_THAN_RELEASE` |
| Self-approval, or the same person approving and publishing (OIDC mode) | `SELF_APPROVAL_FORBIDDEN`, `SAME_ACTOR_PROMOTION_FORBIDDEN` |

Every transition is recorded in the hash-chained governance audit. In Postgres the contract tables come from migration `002_data_contracts.sql`, and `/ready` verifies the contract audit chains as well as the policy chains.

## Boundaries

- Contract roles reuse the policy roles. Organisations whose data owners differ from their policy owners may want dedicated roles.
- The audit hash detects accidental and casual tampering. A database administrator can still rewrite local state; external anchoring is not implemented.
- Publishing a contract doesn't make the data inside it safe. Signed documents can still contain injected instructions, and the runtime treats them as untrusted evidence.
