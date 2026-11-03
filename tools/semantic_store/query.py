"""Bounded, authorization-aware read surface for the candidate semantic store.

This is deterministic graph retrieval, not evidence corroboration or reasoning.
The supplied authorization callback MUST enforce tenant and object permissions.
"""
from __future__ import annotations

from collections import deque
import json
from typing import Any, Callable

from store import SemanticStore

ObjectAuthorizer = Callable[[str, str, str], bool]


def query_context(
    store: SemanticStore,
    *,
    principal: str,
    authorize: ObjectAuthorizer,
    object_id: str,
    revision: str,
    max_hops: int = 1,
    max_nodes: int = 30,
    max_edges: int = 200,
    layers: tuple[str, ...] = ("KNOWLEDGE", "WITNESS"),
) -> dict[str, Any]:
    if not isinstance(principal, str) or not principal.strip():
        raise PermissionError("Authenticated principal is required")
    if not callable(authorize):
        raise PermissionError("An explicit access policy is required")
    if (type(max_hops) is not int or max_hops < 0 or max_hops > 5
            or type(max_nodes) is not int or max_nodes < 1 or max_nodes > 100
            or type(max_edges) is not int or max_edges < 1 or max_edges > 1000):
        raise ValueError("Traversal exceeds bounded query limits")
    if not layers or any(layer not in ("KNOWLEDGE", "WITNESS", "REGIME")
                         for layer in layers):
        raise ValueError("Unsupported graph layer")
    if not authorize(principal, object_id, revision):
        raise PermissionError("Access denied")

    root = store.object_version(object_id, revision)
    if root is None:
        return {
            "schema": "qualityrag.semantic-context/v0.1",
            "status": "NOT_FOUND",
            "nodes": [], "edges": [],
            "admission": "INCONCLUSIVE",
        }

    frontier = deque([(object_id, revision, 0)])
    seen = set()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    truncated = False
    while frontier and len(nodes) < max_nodes:
        node_id, node_revision, depth = frontier.popleft()
        if (node_id, node_revision) in seen:
            continue
        if not authorize(principal, node_id, node_revision):
            continue
        payload = store.object_version(node_id, node_revision)
        if payload is None:
            continue
        seen.add((node_id, node_revision))
        nodes.append({"object_id": node_id, "revision": node_revision,
                      "payload": payload})
        if depth >= max_hops:
            continue
        if len(edges) >= max_edges:
            truncated = True
            break
        remaining = max_edges - len(edges)
        rows = store.db.execute(
            "SELECT edge_id, layer, from_id, from_revision, to_id, "
            "to_revision, relation, properties_json FROM semantic_edges "
            "WHERE from_id=? AND from_revision=? ORDER BY edge_id LIMIT ?",
            (node_id, node_revision, remaining + 1)).fetchall()
        if len(rows) > remaining:
            truncated = True
        for eid, layer, src, src_rev, dest, dest_rev, relation, properties in rows[:remaining]:
            if layer not in layers or not authorize(principal, dest, dest_rev):
                continue
            # Never expose inaccessible target IDs or their relation labels.
            if store.object_version(dest, dest_rev) is None:
                continue
            edges.append({
                "edge_id": eid, "layer": layer,
                "from_id": src, "from_revision": src_rev,
                "to_id": dest, "to_revision": dest_rev,
                "relation": relation, "properties": json.loads(properties),
            })
            if (dest, dest_rev) not in seen:
                frontier.append((dest, dest_rev, depth + 1))

    if frontier:
        truncated = True
    # Edges referencing nodes omitted by the bound must not leak target IDs.
    admitted_ids = {(x["object_id"], x["revision"]) for x in nodes}
    edges = [x for x in edges
             if (x["from_id"], x["from_revision"]) in admitted_ids
             and (x["to_id"], x["to_revision"]) in admitted_ids]
    return {
        "schema": "qualityrag.semantic-context/v0.1",
        "status": "BOUNDED_CONTEXT",
        "nodes": nodes, "edges": edges,
        "admission": "INCONCLUSIVE",
        "verification": "NOT_PERFORMED",
        "limits": {"max_hops": max_hops, "max_nodes": max_nodes,
                   "max_edges": max_edges, "truncated": truncated},
        "boundary": "Returned nodes are structural candidates, not admitted truths. "
                    "Access control is delegated to the caller-supplied policy.",
    }
