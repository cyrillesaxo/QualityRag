"""Bounded functional-evidence discovery. Advisory only; never an admission engine.

Graph nodes and edges are untrusted retrieval hints. No graph relation becomes a
witness, and no proposal modifies the governing PackSpec.
"""
from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json
from typing import Any

from .compiler import compile_pack, evaluate_compiled

SCHEMA = "qualityrag.discovery/v0.1"
RELATIONS = frozenset({
    "IS_A", "HAS_SUBTYPE", "PART_OF", "CONTAINS", "GOVERNS",
    "EXCEPTS", "REQUIRES", "SUPERSEDES", "FUNCTIONAL_SIBLING",
    "ALTERNATIVE_TO", "DEPENDS_ON",
})
OBLIGATION_RELATIONS = frozenset({"EXCEPTS", "REQUIRES", "SUPERSEDES"})
MAX_NODES = 500
MAX_EDGES = 2000


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256


def _validate_graph(graph: dict[str, Any]) -> tuple[dict, dict]:
    if not isinstance(graph, dict):
        raise ValueError("Graph must be an object")
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Graph needs nodes and edges")
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise ValueError("Graph budget exceeded")
    by_id: dict[str, dict] = {}
    for node in nodes:
        if (not isinstance(node, dict) or not _identifier(node.get("id"))
                or node["id"] in by_id):
            raise ValueError("Invalid or duplicate node")
        by_id[node["id"]] = node
    adjacency: dict[str, list] = defaultdict(list)
    for index, edge in enumerate(edges):
        if (not isinstance(edge, dict) or edge.get("relation") not in RELATIONS
                or edge.get("source") not in by_id or edge.get("target") not in by_id):
            raise ValueError("Invalid edge")
        # Edges must cite the source from which the relationship was proposed.
        if not _identifier(edge.get("source_ref")):
            raise ValueError("Edge is missing source_ref")
        adjacency[edge["source"]].append((index, edge))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item: (item[1]["relation"], item[1]["target"], item[0]))
    return by_id, adjacency


def discover(
    pack: dict[str, Any],
    evidence: list[dict[str, Any]],
    graph: dict[str, Any],
    seeds: list[dict[str, str]],
    *,
    as_of: str,
    max_depth: int = 3,
    max_candidates: int = 40,
) -> dict[str, Any]:
    """Propose retrieval targets and missing policy obligations; never return ADMIT.

    seeds = [{"requirement_id": existing PackSpec requirement, "entity_id": graph node}]
    Inferred nodes/edges are untrusted and may be investigated by the host. The
    canonical evidence evaluator receives only the caller's original evidence.
    """
    obligations = compile_pack(pack)
    if (type(max_depth) is not int or not 0 <= max_depth <= 5
            or type(max_candidates) is not int or not 1 <= max_candidates <= 100):
        raise ValueError("Invalid discovery limits")
    if not isinstance(seeds, list) or len(seeds) > 100:
        raise ValueError("Invalid seeds")
    by_id, adjacency = _validate_graph(graph)
    known_requirements = {o.requirement_id for o in obligations}
    obligation_by_id = {o.requirement_id: o for o in obligations}
    baseline = evaluate_compiled(pack, evidence, as_of=as_of)
    pending = {row["requirement_id"] for row in baseline["findings"]
               if row["verdict"] != "ADMIT"}
    normalized_seeds = []
    for seed in seeds:
        if (not isinstance(seed, dict) or seed.get("requirement_id") not in known_requirements
                or seed.get("entity_id") not in by_id):
            raise ValueError("Seed must reference an existing requirement and graph entity")
        normalized_seeds.append((seed["requirement_id"], seed["entity_id"]))
    queue = deque((rid, entity, 0, ()) for rid, entity in sorted(set(normalized_seeds)))
    visited: set[tuple[str, str]] = {(rid, entity) for rid, entity in set(normalized_seeds)}
    candidates, amendments, seen_candidates, seen_amendments = [], [], set(), set()
    traversed = 0
    while queue:
        rid, entity, depth, path = queue.popleft()
        if depth >= max_depth:
            continue
        for index, edge in adjacency.get(entity, ()):
            if traversed >= MAX_EDGES:
                break
            traversed += 1
            target = edge["target"]
            node = by_id[target]
            new_path = (*path, {"source": entity, "target": target,
                                "relation": edge["relation"], "source_ref": edge["source_ref"]})
            key = (rid, target)
            # A relationship never confers provenance, authority, or equivalence.
            if rid in pending and key not in seen_candidates and len(candidates) < max_candidates:
                o = obligation_by_id[rid]
                candidates.append({
                    "requirement_id": rid, "entity_id": target, "relation": edge["relation"],
                    "depth": depth + 1, "path": list(new_path),
                    "candidate_source_ref": node.get("source_ref"),
                    "context_mismatch": (
                        ("scope" in node and node["scope"] != o.required_scope)
                        or (o.required_authority is not None and
                            node.get("authority") != o.required_authority)),
                    "status": "UNVERIFIED_RETRIEVAL_TARGET",
                })
                seen_candidates.add(key)
            if edge["relation"] in OBLIGATION_RELATIONS:
                suggestion = node.get("proposed_requirement_id")
                if (_identifier(suggestion) and suggestion not in known_requirements
                        and suggestion not in seen_amendments and len(amendments) < max_candidates):
                    amendments.append({
                        "proposed_requirement_id": suggestion,
                        "trigger_requirement_id": rid, "relation": edge["relation"],
                        "entity_id": target, "path": list(new_path),
                        "status": "REVIEW_REQUIRED",
                        "reason": "Potential missing policy obligation; not active or authoritative",
                    })
                    seen_amendments.add(suggestion)
            if (rid, target) not in visited:
                visited.add((rid, target))
                queue.append((rid, target, depth + 1, new_path))
    return {
        "schema": SCHEMA, "pack_id": pack["id"], "pack_version": pack["version"],
        "pack_sha256": _digest(pack), "graph_sha256": _digest(graph),
        "baseline_verdict": baseline["verdict"],
        "baseline_findings": baseline["findings"],
        "discovery_verdict": "INCONCLUSIVE",
        "can_generate": False, "policy_changed": False,
        "candidates": candidates, "proposed_obligations": amendments,
        "search": {"visited_states": len(visited), "traversed_edges": traversed,
                   "max_depth": max_depth, "max_candidates": max_candidates,
                   "truncated": len(candidates) >= max_candidates
                       or len(amendments) >= max_candidates or traversed >= MAX_EDGES},
        "limitations": [
            "Relations and source identifiers are untrusted retrieval hints.",
            "No origin independence, authority, truth or semantic equivalence is established.",
            "No proposed obligation alters PackSpec without independent review.",
            "Re-evaluate newly collected authenticated witnesses with the existing unified gate.",
        ],
    }
