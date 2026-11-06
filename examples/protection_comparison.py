"""Synthetic comparison harness: redaction vs references vs purpose-scoped views.

Only synthetic identifiers are used. This is a *functional fixture*, not
evidence of superior semantic accuracy, privacy or compliance. Do not publish
the outputs as an empirical benchmark.
Run: PYTHONPATH=sdk/python python examples/protection_comparison.py
"""
from __future__ import annotations

import json
from qualityrag.protection import Principal, SCHEMA
from qualityrag.protection_attestation import (
    attest_contract, issue_protected_view, verify_protected_release, InMemoryReplayStore,
)

REGISTRY_KEY = b"synthetic-registry-key-for-fixture-only!"
RELEASE_KEY = b"synthetic-release-key-for-fixture-only!"


def run_fixture() -> dict:
    principal = Principal("contract-reader", "demo", frozenset({"payment_review"}))
    # No PANs in source inputs: references and approved derived facts only.
    source = {
        "payment_ref": "ref_synthetic_card_00001",
        "last_four": "4242",
        "expiry_valid": True,
        "payment_terms": "Due within 30 days",
    }
    grant = [{"purpose": "payment_review", "destination": "llm", "operation": "read"}]
    fields = {
        "payment_ref": {"classification": "pci", "mode": "reference", "grants": []},
        "last_four": {"classification": "pci", "mode": "derived", "grants": []},
        "expiry_valid": {"classification": "pci", "mode": "derived", "grants": grant},
        "payment_terms": {"classification": "public", "mode": "plain", "grants": grant},
    }
    contract = {"schema": SCHEMA, "tenant": "demo", "fields": fields}
    attested = attest_contract(contract, REGISTRY_KEY)
    envelope = issue_protected_view(
        source, attested, principal, purpose="payment_review", destination="llm",
        registry_key=REGISTRY_KEY, release_key=RELEASE_KEY, now=1000, ttl_seconds=60)
    scoped = verify_protected_release(
        envelope, principal, destination="llm", purpose="payment_review",
        release_key=RELEASE_KEY, replay_store=InMemoryReplayStore(), now=1001)["view"]

    # Chosen representative baseline policies, not comprehensive products.
    redacted = {"payment_terms": source["payment_terms"]}
    tokenized = {
        "payment_ref": source["payment_ref"],
        "last_four": source["last_four"],
        "expiry_valid": source["expiry_valid"],
        "payment_terms": source["payment_terms"],
    }

    def score(view: dict) -> dict:
        # Rule-based task sufficiency: no LLM inference, no adversarial testing.
        return {
            "can_answer_payment_deadline": "payment_terms" in view,
            "can_answer_expiry_valid": "expiry_valid" in view,
            "exposed_fields": sorted(view),
            "exposed_field_count": len(view),
        }

    return {
        "scope": "synthetic deterministic fixtures only; no measured security result",
        "redaction": score(redacted),
        "tokenization_plus_attributes": score(tokenized),
        "purpose_scoped": score(scoped),
    }


if __name__ == "__main__":
    print(json.dumps(run_fixture(), indent=2, sort_keys=True))
