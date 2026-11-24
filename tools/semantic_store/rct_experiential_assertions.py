"""Bind experiential claims to existing signed custody and PackSpec diagnostics.

The host supplies trust registries and the replay ledger through the existing
custody API. No supplied receipt, quote, or distinct root is proof of truth.
"""
from __future__ import annotations

from hashlib import sha256
from rct_source_custody import assess_source_custody
from store import digest

SCHEMA = "rct.experiential-assertions/v1"
KINDS = frozenset({"CONTEXT", "DECISION", "OUTCOME", "MECHANISM", "CAUSAL", "BOUNDARY"})


def assertion_binding(candidate, claims, pack, witnesses, source_bytes):
    """Validate exact UTF-8 byte anchors and one-to-one claim obligations."""
    if not isinstance(candidate, dict) or not candidate:
        raise ValueError("Candidate representation required")
    if not isinstance(claims, list) or not 1 <= len(claims) <= 32:
        raise ValueError("Bounded assertion inventory required")
    requirements = {r["id"] for r in pack["requirements"]}
    by_id = {w["id"]: w for w in witnesses}
    ids, mapped = set(), set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"id", "kind", "text", "requirement_id", "anchors"}:
            raise ValueError("Invalid assertion fields")
        cid, rid = claim["id"], claim["requirement_id"]
        if (not isinstance(cid, str) or not cid or cid in ids or
                rid not in requirements or rid in mapped or claim["kind"] not in KINDS or
                not isinstance(claim["text"], str) or not 1 <= len(claim["text"]) <= 4000):
            raise ValueError("Invalid or duplicate assertion obligation")
        ids.add(cid)
        mapped.add(rid)
        anchors = claim["anchors"]
        if not isinstance(anchors, list) or len(anchors) > 16:
            raise ValueError("Bounded claim anchors required")
        for a in anchors:
            if not isinstance(a, dict) or set(a) != {"witness_id", "root_id", "start_byte", "end_byte", "quote"}:
                raise ValueError("Invalid claim anchor")
            w = by_id.get(a["witness_id"])
            raw = source_bytes.get(a["root_id"])
            start, end = a["start_byte"], a["end_byte"]
            if (not w or w.get("requirement_id") != rid or w.get("derives_from") != [] or
                    w.get("origin") != a["root_id"] or not isinstance(raw, bytes) or
                    type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw) or
                    not isinstance(a["quote"], str) or raw[start:end] != a["quote"].encode("utf-8")):
                raise ValueError("Claim anchor must match exact primary bytes and obligation")
    if mapped != requirements:
        raise ValueError("Every PackSpec obligation requires an assertion")
    return {"schema": SCHEMA, "candidate_sha256": digest(candidate),
            "claims_sha256": digest(claims), "pack_sha256": digest(pack),
            "root_sha256": {k: sha256(v).hexdigest() for k, v in sorted(source_bytes.items())}}


def assess_experiential_assertions(*, candidate, claims, **custody_args):
    binding = assertion_binding(candidate, claims, custody_args["evidence_pack"],
                                custody_args["witnesses"], custody_args["source_bytes"])
    if custody_args["observations"].get("experiential_binding") != binding:
        raise ValueError("Signed observations must bind exact experiential assertions")
    custody = assess_source_custody(**custody_args)
    blockers = set(custody["blockers"])
    coverage = []
    for claim in claims:
        if not claim["anchors"]:
            blockers.add("CLAIM_ANCHOR_MISSING")
        if claim["kind"] == "CAUSAL":
            blockers.add("CAUSAL_SUPPORT_UNVERIFIED")
        coverage.append({"id": claim["id"], "requirement_id": claim["requirement_id"],
                         "kind": claim["kind"], "exact_primary_anchor_count": len(claim["anchors"]),
                         "semantic_support": "UNKNOWN"})
    result = {"schema": SCHEMA, "binding": binding, "claims": coverage,
              "custody_receipt_sha256": custody["fingerprint"],
              "verdict": "REFUSE" if custody["verdict"] == "REFUSE" else "INCONCLUSIVE",
              "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
              "blockers": sorted(blockers | {"ASSERTION_ENTAILMENT_UNVERIFIED",
                                             "REPRESENTATION_COMPLETENESS_UNVERIFIED"})}
    result["fingerprint"] = digest(result)
    return result
