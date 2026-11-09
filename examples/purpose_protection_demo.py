"""Synthetic reference-only signed protection demonstration.

Run: PYTHONPATH=sdk/python python examples/purpose_protection_demo.py
NOT a production vault or PCI compliance demonstration.
"""
from qualityrag.protection import Principal, SCHEMA, ProtectionDenied
from qualityrag.protection_lifecycle import InMemoryPolicyAuthority
from qualityrag.protection_attestation import (
    attest_contract, issue_protected_view, verify_protected_release, InMemoryReplayStore,
)

# Illustrative in-process signing keys. Real keys belong in independently
# authenticated, access-controlled services and must never reach an LLM.
registry_key = b"synthetic-registry-demo-key-32-bytes!"
release_key = b"synthetic-release-demo-key-32-bytes!"

principal = Principal("contract-analyst", "tenant-demo", frozenset({"review"}))
policy_authority = InMemoryPolicyAuthority()
policy_authority.publish(tenant="tenant-demo", policy_id="demo-contract", version=1)
record = {"payment_ref": "ref_demo_reference_0001", "last_four": "4242",
          "obligation": "Invoice due within 30 days"}
grant = [{"purpose": "review", "destination": "model", "operation": "read"}]
contract = {
    "schema": SCHEMA, "tenant": "tenant-demo",
    "policy_id": "demo-contract", "policy_version": 1,
    "fields": {
        "payment_ref": {"classification": "pci", "mode": "reference", "grants": grant},
        "last_four": {"classification": "pci", "mode": "derived", "grants": grant},
        "obligation": {"classification": "public", "mode": "plain", "grants": grant},
    },
}

# Contract signing is performed by a trusted registry, never an untrusted source.
attested = attest_contract(contract, registry_key)
envelope = issue_protected_view(
    record, attested, principal, purpose="review", destination="model",
    registry_key=registry_key, release_key=release_key,
    policy_authority=policy_authority)
print("Protected model view:", envelope["receipt"]["protected_view"]["view"])

# Release happens in an independent trusted service, using a one-time nonce store.
replay_store = InMemoryReplayStore()
decision = verify_protected_release(
    envelope, principal, destination="model", purpose="review",
    release_key=release_key, replay_store=replay_store,
    policy_authority=policy_authority)
print("Authorized operation:", decision["decision"])

try:
    verify_protected_release(
        envelope, principal, destination="model", purpose="review",
        release_key=release_key, replay_store=replay_store)
except ProtectionDenied as exc:
    print("Second use rejected:", str(exc))
