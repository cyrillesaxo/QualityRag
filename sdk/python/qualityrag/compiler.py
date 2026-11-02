"""Experimental PackSpec-to-ConstraintIR compiler and witness/gap evaluator.

Untrusted witness metadata is never evidence of source authenticity.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass(frozen=True)
class Obligation:
    requirement_id: str
    min_origins: int
    max_age_seconds: int | None
    required_scope: str
    required_authority: str | None

def compile_pack(pack: dict[str, Any]) -> tuple[Obligation, ...]:
    if not isinstance(pack, dict) or not isinstance(pack.get("id"), str) or not pack["id"].strip() or not isinstance(pack.get("version"), str) or not pack["version"].strip():
        raise ValueError("Invalid pack identity")
    requirements = pack.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("Pack needs requirements")
    output, seen = [], set()
    for r in requirements:
        if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not r["id"].strip() or r["id"] in seen:
            raise ValueError("Invalid/duplicate requirement id")
        seen.add(r["id"])
        n = r.get("min_independent_sources", 1)
        age = r.get("max_age_seconds")
        scope = r.get("scope", "global")
        authority = r.get("authority")
        if type(n) is not int or n < 1 or (age is not None and (type(age) is not int or age < 0)):
            raise ValueError("Invalid thresholds")
        if not isinstance(scope, str) or not scope.strip() or (authority is not None and (not isinstance(authority, str) or not authority.strip())):
            raise ValueError("Invalid scope/authority")
        output.append(Obligation(r["id"], n, age, scope, authority))
    return tuple(output)

def _instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Invalid datetime")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Datetime requires timezone")
    return result.astimezone(timezone.utc)

def evaluate_compiled(pack: dict[str, Any], evidence: list[dict[str, Any]], *, as_of: str) -> dict[str, Any]:
    obligations = compile_pack(pack)
    if not isinstance(evidence, list):
        raise ValueError("Evidence must be a list")
    now = _instant(as_of)
    findings, graph_nodes, dependencies = [], [], {}
    for o in obligations:
        origins, reasons, conflicts = set(), set(), False
        for row in evidence:
            if not isinstance(row, dict) or row.get("requirement_id") != o.requirement_id:
                continue
            if not all(isinstance(row.get(k), str) and row[k].strip() for k in ("id", "origin", "source_ref", "observed_at")):
                reasons.add("INVALID_WITNESS")
                continue
            if row.get("status") not in ("SUPPORTS", "CONTRADICTS", "UNKNOWN"):
                reasons.add("INVALID_WITNESS")
                continue
            try:
                age = (now - _instant(row["observed_at"])).total_seconds()
            except (ValueError, TypeError):
                reasons.add("INVALID_WITNESS")
                continue
            graph_nodes.append({"id": row["id"], "origin": row["origin"], "requirement_id": o.requirement_id})
            dependencies.setdefault((o.requirement_id, row["origin"]), []).append(row["id"])
            if age < 0:
                reasons.add("FUTURE_WITNESS")
                continue
            if o.max_age_seconds is not None and age > o.max_age_seconds:
                reasons.add("STALE_WITNESS")
                continue
            if row.get("scope", "global") != o.required_scope:
                reasons.add("SCOPE_MISMATCH")
                continue
            if o.required_authority is not None and row.get("authority") != o.required_authority:
                reasons.add("AUTHORITY_MISMATCH")
                continue
            if row["status"] == "CONTRADICTS":
                conflicts = True
            elif row["status"] == "SUPPORTS":
                origins.add(row["origin"])
            else:
                reasons.add("UNKNOWN_WITNESS")
        if conflicts:
            verdict = "REFUSE"
            reasons.add("CONTRADICTION")
        elif len(origins) < o.min_origins:
            verdict = "INCONCLUSIVE"
            reasons.add("INSUFFICIENT_INDEPENDENT_EVIDENCE")
        else:
            verdict = "ADMIT"
        findings.append({"requirement_id": o.requirement_id, "verdict": verdict,
                         "independent_sources": len(origins), "missing_sources": max(0, o.min_origins - len(origins)),
                         "reasons": sorted(reasons)})
    verdict = ("REFUSE" if any(f["verdict"] == "REFUSE" for f in findings) else
               "INCONCLUSIVE" if any(f["verdict"] == "INCONCLUSIVE" for f in findings) else "ADMIT")
    return {
        "schema": "qualityrag.compiled-result/v0.1",
        "pack_id": pack["id"], "pack_version": pack["version"], "verdict": verdict,
        "constraint_ir": [vars(o) for o in obligations],
        "findings": findings,
        "witness_graph": {
            "nodes": graph_nodes,
            "dependent_groups": [{"requirement_id": req, "origin": origin, "witness_ids": sorted(ids)}
                                 for (req, origin), ids in sorted(dependencies.items()) if len(ids) > 1]
        },
        "wgap": [{"requirement_id": f["requirement_id"], "missing_sources": f["missing_sources"],
                  "reasons": f["reasons"]} for f in findings if f["verdict"] != "ADMIT"]
    }
