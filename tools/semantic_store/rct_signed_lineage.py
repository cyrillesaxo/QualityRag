"""RCT v1.8: signed observation and declared derivation-lineage diagnostics.

Uses existing Ed25519 policy/observation verification and durable nonce guard.
Proves authenticity of signed *records* from configured keys, NOT source truth,
real-world origin independence, witness adequacy, or omission safety.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

_PACKSPEC = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(_PACKSPEC) not in sys.path:
    sys.path.insert(0, str(_PACKSPEC))
from signed_bundles import verify_policy, verify_attestation, SignatureError
from rct_joint_governance import evaluate_joint_governance
from store import digest

SCHEMA = "rct.signed-lineage-diagnostics/v1.8"
MAX_WITNESSES = 200
MAX_ANCESTRY_EDGES = 1000


def _lineage(witnesses: list[dict]) -> dict:
    """Resolve full root ancestry and group shared-root claims.

    An origin is an *asserted* root identifier. The graph identifies repeated
    roots in signed records but cannot prove different roots independent.
    """
    if not isinstance(witnesses, list) or not 1 <= len(witnesses) <= MAX_WITNESSES:
        raise ValueError("Bounded nonempty witness collection required")
    lookup = {}
    total_edges = 0
    for item in witnesses:
        if not isinstance(item, dict):
            raise ValueError("Invalid witness")
        wid = item.get("id")
        parents = item.get("derives_from")
        origin = item.get("origin")
        if not isinstance(wid, str) or not wid or wid in lookup:
            raise ValueError("Witness IDs must be unique and nonempty")
        if (not isinstance(origin, str) or not origin
                or not isinstance(parents, list)
                or any(not isinstance(x, str) or not x for x in parents)
                or len(set(parents)) != len(parents)):
            raise ValueError("Explicit and unique parent witness IDs required")
        if not parents and (not isinstance(item.get("source_ref"), str)
                            or not item["source_ref"]):
            raise ValueError("Root witness needs a source reference")
        lookup[wid] = item
        total_edges += len(parents)
    if total_edges > MAX_ANCESTRY_EDGES:
        raise ValueError("Lineage edge bound exceeded")
    for wid, item in lookup.items():
        for parent in item["derives_from"]:
            if parent not in lookup:
                raise ValueError("Unresolved witness ancestor: " + parent)
            if parent == wid:
                raise ValueError("Self-dependent witness")
    visiting = set()
    cache = {}
    def roots(wid):
        if wid in visiting:
            raise ValueError("Cycle in witness derivation graph")
        if wid in cache:
            return cache[wid]
        visiting.add(wid)
        item = lookup[wid]
        outcome = (frozenset((item["origin"],)) if not item["derives_from"] else
                   frozenset().union(*(roots(p) for p in item["derives_from"])))
        visiting.remove(wid)
        if not outcome:
            raise ValueError("Unrooted derivation")
        cache[wid] = outcome
        return outcome
    ancestry = {wid: sorted(roots(wid)) for wid in sorted(lookup)}

    # Connected components in an overlap graph; any ancestry root shared by
    # multiple supportive records collapses those witnesses into one group.
    grouped = defaultdict(list)
    for wid, row in lookup.items():
        if row.get("status") == "SUPPORTS":
            grouped[row.get("requirement_id")].append(wid)
    components = {}
    for req, ids in sorted(grouped.items()):
        remaining = set(ids)
        groups = []
        while remaining:
            current = {min(remaining)}
            remaining -= current
            frontier = set(ancestry[next(iter(current))])
            changed = True
            while changed:
                members = {wid for wid in remaining
                           if frontier.intersection(ancestry[wid])}
                changed = bool(members)
                remaining -= members
                current.update(members)
                for wid in members:
                    frontier.update(ancestry[wid])
            groups.append({"witness_ids": sorted(current),
                           "declared_roots": sorted(frontier)})
        components[req] = sorted(groups, key=lambda item: item["witness_ids"])
    return {
        "witness_roots": ancestry,
        "support_components": components,
        "derived_witnesses": sorted(wid for wid, item in lookup.items()
                                    if item["derives_from"]),
        "declared_root_identity_only": True,
        "lineage_provenance": "SIGNED_RECORDS_NOT_AUTHENTICATED_PRIMARY_SOURCES",
    }


def assess_signed_lineage(*, lens: dict, reviewed_ir: dict, ir_binding: dict,
                          evidence_pack: dict, witness_mapping: dict,
                          signed_policy: dict, signed_observations: dict,
                          policy_keys: dict, attestor_keys: dict,
                          service: str, environment: str, minimum_sequence: int,
                          nonce_accepted, witnesses: list[dict],
                          observations: dict, as_of: str) -> dict:
    """Verify signatures/replay, then run unchanged existing governance engines.

    Failures of a signature, source binding or malformed lineage are errors.
    No generator is available through this diagnostic API.
    """
    policy = verify_policy(signed_policy, policy_keys, service=service,
                           environment=environment, as_of=as_of,
                           minimum_sequence=minimum_sequence)
    if policy["ir"] != reviewed_ir:
        raise ValueError("Signed policy IR does not match governed IR")
    if not isinstance(observations, dict):
        raise ValueError("Observations required")
    binding = observations.get("rct_binding")
    if not isinstance(binding, dict) or binding != {
            "lens_fingerprint": lens.get("fingerprint"),
            "source_sha256": lens.get("source_sha256"),
            "evidence_pack_sha256": digest(evidence_pack),
            "witness_mapping_sha256": witness_mapping.get("fingerprint"),
        }:
        raise ValueError("Signed observations must bind exact RCT lens and evidence mapping")
    # The lineage is included within each signed witness record; the signature
    # binds the precise parent relationships without certifying their accuracy.
    verified = verify_attestation(
        signed_observations, attestor_keys,
        policy_signature=signed_policy["signature"],
        service=service, environment=environment, as_of=as_of,
        witnesses=witnesses, observations=observations,
        nonce_accepted=nonce_accepted)
    if verified is not True:
        raise SignatureError("Attestation not accepted")
    ancestry = _lineage(witnesses)
    joint = evaluate_joint_governance(
        lens=lens, reviewed_ir=reviewed_ir, ir_binding=ir_binding,
        evidence_pack=evidence_pack, witness_mapping=witness_mapping,
        witnesses=witnesses, observations=observations, as_of=as_of)
    # Even distinct signed root IDs are not independently authenticated sources.
    # An actual common root is a positive dependency finding, not full proof.
    needs = {r["id"]: r.get("min_independent_sources", 1)
             for r in evidence_pack["requirements"]}
    coverage = {}
    shared = False
    for requirement, minimum in sorted(needs.items()):
        groups = ancestry["support_components"].get(requirement, [])
        if any(len(group["witness_ids"]) > 1 for group in groups):
            shared = True
        coverage[requirement] = {
            "declared_lineage_component_count": len(groups),
            "declared_minimum": minimum,
            "missing_components": max(0, minimum - len(groups)),
            "proven_independence": "UNKNOWN",
        }
    blockers = sorted(set(joint["blockers"] + [
        "SIGNED_WITNESS_CONTENT_DOES_NOT_PROVE_SOURCE_TRUTH",
        "DISTINCT_ROOT_IDENTITIES_NOT_INDEPENDENCE_ATTESTATION",
        "RCT_OMISSION_MEANING_NOT_VERIFIED",
    ] + (["SHARED_ANCESTOR_DEPENDENCY"] if shared else [])))
    if any(value["missing_components"] for value in coverage.values()):
        blockers.append("INSUFFICIENT_DECLARED_LINEAGE_COMPONENTS")
    receipt = {
        "schema": SCHEMA,
        "lens_fingerprint": lens["fingerprint"],
        "signed_policy_key_id": signed_policy["key_id"],
        "signed_evidence_key_id": signed_observations["key_id"],
        "verified_record_signature": True,
        "lineage": ancestry,
        "declared_component_coverage": coverage,
        "joint_governance_receipt_sha256": joint["fingerprint"],
        "joint_governance": joint,
        "verdict": "REFUSE" if joint["verdict"] == "REFUSE" else "INCONCLUSIVE",
        "can_generate": False,
        "qualityrag_admission": "INCONCLUSIVE",
        "blockers": sorted(set(blockers)),
    }
    receipt["fingerprint"] = digest(receipt)
    return receipt
