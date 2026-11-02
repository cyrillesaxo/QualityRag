"""QualityRag deterministic evidence gate; v0.1 API."""
from datetime import datetime, timezone
from typing import Any

def evaluate(pack: dict[str, Any], evidence: list[dict[str, Any]], *, as_of: str | None = None) -> dict[str, Any]:
    """Evaluate the supplied policy and evidence metadata, not source truth."""
    now = _date(as_of) if as_of else datetime.now(timezone.utc)
    if not isinstance(pack, dict) or not pack.get("id") or not pack.get("version"):
        raise ValueError("pack must have id and version")
    requirements = pack.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("pack must have nonempty requirements")
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a list")
    ids = [r.get("id") for r in requirements if isinstance(r, dict)]
    if len(ids) != len(requirements) or any(not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("requirement IDs must be unique nonempty strings")
    findings = []
    for req in requirements:
        rid = req["id"]
        minimum = req.get("min_independent_sources", 1)
        max_age = req.get("max_age_seconds")
        if type(minimum) is not int or minimum < 1 or (max_age is not None and (type(max_age) is not int or max_age < 0)):
            raise ValueError("invalid requirement thresholds")
        rows = [x for x in evidence if isinstance(x, dict) and x.get("requirement_id") == rid]
        valid = []
        reasons = []
        contradicted = False
        for x in rows:
            if not all(isinstance(x.get(k), str) and x.get(k) for k in ("id", "origin", "source_ref", "observed_at")):
                reasons.append("INVALID_EVIDENCE")
                continue
            if x.get("status") not in ("SUPPORTS", "CONTRADICTS", "UNKNOWN"):
                reasons.append("INVALID_EVIDENCE")
                continue
            try:
                age = (now - _date(x["observed_at"])).total_seconds()
            except (ValueError, TypeError):
                reasons.append("INVALID_EVIDENCE")
                continue
            if age < 0:
                reasons.append("FUTURE_EVIDENCE")
                continue
            if max_age is not None and age > max_age:
                reasons.append("STALE_EVIDENCE")
                continue
            if x["status"] == "CONTRADICTS":
                contradicted = True
            elif x["status"] == "SUPPORTS":
                valid.append(x)
            else:
                reasons.append("UNKNOWN_EVIDENCE")
        count = len({x["origin"] for x in valid})
        if contradicted:
            verdict = "REFUSE"
            reasons.append("CONTRADICTION")
        elif count < minimum:
            verdict = "INCONCLUSIVE"
            reasons.append("INSUFFICIENT_INDEPENDENT_EVIDENCE")
        else:
            verdict = "ADMIT"
        findings.append({"requirement_id": rid, "verdict": verdict, "independent_sources": count, "reasons": sorted(set(reasons))})
    result = "REFUSE" if any(x["verdict"] == "REFUSE" for x in findings) else "INCONCLUSIVE" if any(x["verdict"] == "INCONCLUSIVE" for x in findings) else "ADMIT"
    return {"schema": "qualityrag.result/v0.1", "pack_id": pack["id"], "pack_version": pack["version"], "verdict": result, "findings": findings}

def _date(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)
