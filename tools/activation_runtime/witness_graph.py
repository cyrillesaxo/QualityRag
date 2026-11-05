"""Witness derivation graph with source roots, custody and root-collapsing independence.

A witness either observes an original source (a *root* witness, identified by the
SHA-256 of the custodied original bytes) or is derived from other witnesses (a copy,
excerpt, translation or summary). Independence is computed over source roots, not
witness labels: witnesses whose ancestry shares any root are one source of evidence,
so a mirror of a document can never corroborate the document.

Exact-information preservation is satisfied only by enough root-independent,
fresh, supporting witnesses; any contradicting witness refuses it, and stale,
unknown or missing witnesses leave it UNKNOWN. This is a finite structural check;
it does not authenticate sources. Original APX grouping verifies the declared root
groups; a discrepancy or unavailable canonical runtime refuses independence.
"""
from __future__ import annotations

from datetime import datetime

from .common import HEX, fingerprint, identity

MAX_WITNESSES = 1000
MAX_PARENTS = 16
STATUSES = {"SUPPORTS", "CONTRADICTS", "UNKNOWN"}


def _instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp required")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return moment


def build(witnesses: list[dict]) -> dict:
    """Validate witnesses and compute each one's source roots. Refuses cycles and dangling parents."""
    if not isinstance(witnesses, list) or not 1 <= len(witnesses) <= MAX_WITNESSES:
        raise ValueError("Bounded nonempty witness list required")
    by_id = {}
    for w in witnesses:
        if not isinstance(w, dict) or set(w) - {"id", "obligation", "status", "observed_at", "source_sha256",
                                                 "derived_from", "custody", "transform"}:
            raise ValueError("Unsupported witness fields")
        wid = identity(w.get("id"))
        if wid in by_id:
            raise ValueError("Duplicate witness ID")
        identity(w.get("obligation"))
        if w.get("status") not in STATUSES:
            raise ValueError("Witness status must be SUPPORTS, CONTRADICTS or UNKNOWN")
        _instant(w.get("observed_at"))
        parents = w.get("derived_from", [])
        root = w.get("source_sha256")
        if root is not None:
            if parents:
                raise ValueError("A witness is either a source observation or derived, not both")
            if not isinstance(root, str) or not HEX.fullmatch(root):
                raise ValueError("Source witness needs the SHA-256 of the custodied original")
            custody = w.get("custody")
            if not isinstance(custody, dict) or not isinstance(custody.get("custodian"), str) or not custody["custodian"]:
                raise ValueError("Source witness needs a custodian")
        else:
            if (not isinstance(parents, list) or not 1 <= len(parents) <= MAX_PARENTS
                    or len(set(parents)) != len(parents)):
                raise ValueError("Derived witness needs bounded unique parents")
            if not isinstance(w.get("transform"), str) or not w["transform"]:
                raise ValueError("Derived witness must name its transform")
        by_id[wid] = w
    roots: dict[str, frozenset] = {}
    visiting: set[str] = set()

    def resolve(wid: str) -> frozenset:
        if wid in roots:
            return roots[wid]
        if wid not in by_id:
            raise ValueError("Derived witness references an unknown parent")
        if wid in visiting:
            raise ValueError("Witness derivation cycle")
        visiting.add(wid)
        w = by_id[wid]
        if w.get("source_sha256") is not None:
            result = frozenset([w["source_sha256"]])
        else:
            result = frozenset().union(*(resolve(p) for p in w["derived_from"]))
        visiting.discard(wid)
        roots[wid] = result
        return result

    for wid in by_id:
        resolve(wid)
    return {"witnesses": by_id, "roots": {k: sorted(v) for k, v in roots.items()},
            "graph_sha256": fingerprint(sorted(witnesses, key=lambda w: w["id"]))}


def independent_groups(graph: dict, witness_ids: list[str]) -> list[list[str]]:
    """Group witnesses whose ancestry shares any source root (transitively). Each group counts once."""
    parent = {wid: wid for wid in witness_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner: dict[str, str] = {}
    for wid in witness_ids:
        for root in graph["roots"][wid]:
            if root in owner:
                parent[find(wid)] = find(owner[root])
            else:
                owner[root] = wid
    groups: dict[str, list[str]] = {}
    for wid in witness_ids:
        groups.setdefault(find(wid), []).append(wid)
    local=sorted(sorted(g) for g in groups.values())
    if not local:return []
    from .native_witness import build as canonical_graph
    projected=[];expected=[]
    for group in local:
        key=fingerprint(sorted({r for wid in group for r in graph["roots"][wid]}))
        projected.extend({"id":wid,"independence_key":key} for wid in group)
        if len(group)>1:expected.append({"key":key,"witness_ids":group,"independence_credit":"withheld"})
    native=canonical_graph(projected)
    if native!={"nodes":projected,"dependentGroups":sorted(expected,key=lambda row:row["key"])}:
        raise ValueError("Canonical WitnessGraph discrepancy; independence refused")
    native_groups=[row["witness_ids"] for row in native["dependentGroups"]]
    grouped={wid for group in native_groups for wid in group}
    return sorted(native_groups+[[row["id"]] for row in projected if row["id"] not in grouped])


def assess_exact(graph: dict, obligation: str, *, as_of: str, max_age_seconds: int | None,
                 min_independent_roots: int = 1) -> dict:
    """Can these witnesses satisfy exact-information preservation for one obligation?"""
    if type(min_independent_roots) is not int or min_independent_roots < 1:
        raise ValueError("Positive independence threshold required")
    if max_age_seconds is not None and (type(max_age_seconds) is not int or max_age_seconds < 0):
        raise ValueError("Invalid freshness bound")
    now = _instant(as_of)
    rows = [w for w in graph["witnesses"].values() if w["obligation"] == obligation]
    reasons, fresh_support = set(), []
    contradicted = []
    for w in rows:
        age = (now - _instant(w["observed_at"])).total_seconds()
        if age < 0:
            reasons.add("FUTURE_WITNESS")
            continue
        if max_age_seconds is not None and age > max_age_seconds:
            reasons.add("STALE_WITNESS")
            continue
        if w["status"] == "CONTRADICTS":
            contradicted.append(w["id"])
        elif w["status"] == "SUPPORTS":
            fresh_support.append(w["id"])
        else:
            reasons.add("UNKNOWN_WITNESS")
    groups = independent_groups(graph, fresh_support)
    if not rows:
        reasons.add("MISSING_WITNESS")
    if contradicted:
        verdict = "UNSAT"
        reasons.add("CONTRADICTION")
    elif len(groups) >= min_independent_roots:
        verdict = "SAT"
    else:
        verdict = "UNKNOWN"
        reasons.add("INSUFFICIENT_INDEPENDENT_ROOTS")
    return {"schema": "qualityrag.witness-assessment/v1", "obligation": obligation,
            "finite_constraint_result": verdict, "independent_roots": len(groups),
            "independent_groups": groups, "contradicting_witnesses": sorted(contradicted),
            "reasons": sorted(reasons), "graph_sha256": graph["graph_sha256"],
            "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
            "scope": "FINITE_DECLARED_WITNESS_GRAPH_SOURCE_AUTHENTICITY_UNVERIFIED"}


def gate_evidence(graph: dict) -> list[dict]:
    """Project witnesses into QualityRag v0.1 evidence rows with origin = root group.

    qualityrag.evaluate counts distinct origins, so derived copies of one source collapse
    into a single origin instead of being counted as independent corroboration.
    """
    rows = []
    for obligation in sorted({w["obligation"] for w in graph["witnesses"].values()}):
        ids = sorted(w["id"] for w in graph["witnesses"].values() if w["obligation"] == obligation)
        for group in independent_groups(graph, ids):
            origin = "roots:" + fingerprint(sorted({r for wid in group for r in graph["roots"][wid]}))[:32]
            for wid in group:
                w = graph["witnesses"][wid]
                rows.append({"id": wid, "requirement_id": obligation, "origin": origin,
                             "source_ref": "witness:" + wid, "status": w["status"], "observed_at": w["observed_at"]})
    return rows
