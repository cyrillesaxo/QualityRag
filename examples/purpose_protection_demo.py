"""Synthetic demonstration only. This does not vault, encrypt, or inspect real PANs.

Run: PYTHONPATH=sdk/python python examples/purpose_protection_demo.py
"""
from qualityrag.protection import Principal, protect, authorize_release, SCHEMA

principal = Principal("contract-analyst", "tenant-demo", frozenset({"review"}))
# This opaque reference is illustrative; a real one must come from an isolated vault.
record = {"payment_ref": "ref_demo_reference_0001", "last_four": "4242",
          "obligation": "Invoice due within 30 days"}
grant = [{"purpose": "review", "destination": "model", "operation": "read"}]
contract = {
    "schema": SCHEMA, "tenant": "tenant-demo",
    # Prototype-only assertion. A production service MUST verify provenance itself.
    "authenticated": True,
    "fields": {
        "payment_ref": {"classification": "pci", "mode": "reference", "grants": grant},
        "last_four": {"classification": "pci", "mode": "derived", "grants": grant},
        "obligation": {"classification": "public", "mode": "plain", "grants": grant},
    },
}

view = protect(record, contract, principal, purpose="review", destination="model")
print("Protected model view:", view["view"])
# Policy demonstration only: not a cryptographically authenticated release receipt.
print("Reference-only check:", authorize_release(
    view, principal, destination="model", purpose="review")["decision"])
