"""Finite, source-bound AST grammar *candidate* discovery for RCT research.

No general semantic understanding, novel mathematical invention, authenticated
provenance, or QualityRag policy admission is claimed. No inference from prose.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from rct_lens import persist_lens
from store import digest, canonical_bytes

SOURCE_SCHEMA = "rct.structured-ast/v1"
DISCOVERY_SCHEMA = "rct.grammar-candidate/v0.7"
MAX_FACTS = 10000

def _ident(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 160 and value.strip() == value

def _validate(source: dict) -> list[dict]:
    if not isinstance(source, dict) or source.get("schema") != SOURCE_SCHEMA:
        raise ValueError("Unsupported structured source schema")
    facts = source.get("facts")
    if not isinstance(facts, list) or not facts or len(facts) > MAX_FACTS:
        raise ValueError("Facts must be a nonempty bounded list")
    seen = set()
    for fact in facts:
        if not isinstance(fact, dict) or not all(_ident(fact.get(k)) for k in
                ("id", "subject", "predicate", "object", "source_ref")):
            raise ValueError("Each fact requires identifiers and source_ref")
        if fact["id"] in seen:
            raise ValueError("Duplicate fact id")
        seen.add(fact["id"])
    return facts

def discover_grammars(source: dict) -> list[dict]:
    """Discover reusable finite grammar candidates from typed AST relationships.

    Grammar 1 joins 'part_of' with 'is_a' to group typed members.
    Grammar 2 factors multiple 'converges_to' edges by shared target.
    Neither derives truth, exhaustiveness, visual correctness or equivalence.
    """
    facts = _validate(source)
    types: dict[str, list[dict]] = defaultdict(list)
    for f in facts:
        if f["predicate"] == "is_a":
            types[f["subject"]].append(f)

    groups: dict[tuple, dict] = {}
    for f in facts:
        if f["predicate"] == "part_of":
            for t in types[f["subject"]]:
                key = ("typed_parts", f["object"], t["object"])
                slot = groups.setdefault(key, {"kind": "typed_parts", "root": f["object"],
                                                "member_type": t["object"], "members": {},
                                                "support_ids": set()})
                slot["members"][f["subject"]] = sorted({f["id"], t["id"]})
                slot["support_ids"].update((f["id"], t["id"]))
        if f["predicate"] == "converges_to":
            key = ("shared_anchor", f["object"], "converges_to")
            slot = groups.setdefault(key, {"kind": "shared_anchor", "root": f["object"],
                                            "member_type": "converging_edges", "members": {},
                                            "support_ids": set()})
            slot["members"][f["subject"]] = [f["id"]]
            slot["support_ids"].add(f["id"])

    out = []
    for key, g in sorted(groups.items()):
        if g["kind"] == "shared_anchor" and len(g["members"]) < 2:
            continue
        out.append({"kind": g["kind"], "root": g["root"],
                    "member_type": g["member_type"],
                    "members": sorted(g["members"]),
                    "member_support": {k: g["members"][k] for k in sorted(g["members"])},
                    "source_fact_ids": sorted(g["support_ids"]),
                    "verification": "UNVERIFIED_STRUCTURAL_PATTERN"})
    return out

def compile_discovered_lens(source: dict, *, lens_id: str, purpose: str,
                             kind: str, root: str, member_type: str,
                             closure_claim: dict | None = None) -> dict:
    """Build a purpose-specific lens from discovered grammar candidates.

    closure_claim is an unverified, source-cited assertion; even when present
    the result never asserts global completeness or QualityRag admission.
    """
    facts = _validate(source)
    if not all(_ident(x) for x in (lens_id, purpose, kind, root, member_type)):
        raise ValueError("Lens fields required")
    if kind not in ("typed_parts", "shared_anchor"):
        raise ValueError("Unsupported grammar kind")
    matches = [g for g in discover_grammars(source)
               if (g["kind"], g["root"], g["member_type"]) == (kind, root, member_type)]
    selected = matches[0] if matches else None
    closure = None
    if closure_claim is not None:
        if not isinstance(closure_claim, dict) or not all(
                _ident(closure_claim.get(k)) for k in ("statement", "source_ref", "reviewer_label")):
            raise ValueError("Closure claim requires statement, source_ref and reviewer label")
        closure = dict(closure_claim)
        closure["authentication"] = "UNVERIFIED_CLOSURE_ASSERTION"

    by_id = {f["id"]: f for f in facts}
    support = (selected or {}).get("source_fact_ids", [])
    claims = [
        {"distinction": f["predicate"], "fact_id": fid,
         "source_ref": f["source_ref"],
         "fact_sha256": digest(f),
         "status": "UNVERIFIED_SOURCE_CLAIM"}
        for fid in support for f in [by_id[fid]]
    ]
    result = {
        "schema": "rct.source-lens/v0.6",  # Existing fail-closed persistence boundary
        "discovery_schema": DISCOVERY_SCHEMA,
        "lens_id": lens_id, "purpose": purpose,
        "source_sha256": digest(source),
        "required": [kind, root, member_type],
        "permitted_omissions": [],
        "candidate_claims": claims,
        "candidate_grammar": selected,
        "unresolved": [] if selected else ["matching_structural_grammar"],
        "local_coverage": "CANDIDATE_STRUCTURAL_GROUP_FOUND" if selected else "UNKNOWN",
        "closure_claim": closure,
        "exhaustiveness": "UNKNOWN",
        "qualityrag_admission": "INCONCLUSIVE",
        "source_authenticity": "UNVERIFIED",
        "packspec_completeness": "UNKNOWN",
        "grammar": "FINITE_TYPED_AST_REWRITES_ONLY",
        "cost_proxy": {
            "input_fact_count": len(facts),
            "active_member_count": len(selected["members"]) if selected else 0,
            "candidate_count": len(discover_grammars(source)),
            "measured_runtime": False,
            "construction_cost_included": False,
        },
        "limitations": [
            "Closed-world completeness is not established",
            "Transformation is not a proof of task-level semantic sufficiency",
            "Rule templates are existing finite patterns, not invented grammar",
        ],
    }
    result["fingerprint"] = digest(result)
    return result

__all__ = ["discover_grammars", "compile_discovered_lens", "persist_lens"]
