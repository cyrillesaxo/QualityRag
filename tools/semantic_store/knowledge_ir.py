"""Read-only bridge from reviewed PackSpec ConstraintIR to candidate KnowledgeIR.

This module compiles *records*, never claims or automatically verified meaning.
It does not execute deferred predicates or promote reviewer labels to authority.
"""
from __future__ import annotations

from typing import Any

from store import digest


IR_SCHEMA = "qualityrag.constraint-ir/v1"
KNOWLEDGE_SCHEMA = "qualityrag.knowledge-ir/v0.1"
KINDS = {"EVIDENCE_PRESENCE", "TEMPORAL", "AUTHORITY", "PROBE", "PREDICATE"}


class KnowledgeIRValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise KnowledgeIRValidationError(message)


def compile_constraint_ir(ir: dict[str, Any]) -> dict[str, Any]:
    """Preserve source identity, review provenance and all deferred obligations."""
    _require(isinstance(ir, dict) and ir.get("schema") == IR_SCHEMA,
             "Expected QualityRag reviewed ConstraintIR v1")
    source = ir.get("source")
    _require(isinstance(source, dict), "Missing source record")
    source_hash = source.get("sha256")
    _require(isinstance(source_hash, str) and len(source_hash) == 64
             and all(c in "0123456789abcdef" for c in source_hash),
             "Missing valid source SHA-256")
    nodes = ir.get("nodes")
    _require(isinstance(nodes, list) and len(nodes) > 0, "No reviewed nodes")
    _require(ir.get("scope") == "INSPECTION_DERIVED_CANDIDATES_ONLY",
             "Unrecognized inspection scope")
    _require(ir.get("assurance") == "NO_AUTOMATIC_SEMANTIC_ENFORCEMENT",
             "Unknown semantic assurance boundary")
    expected_hash = digest({"source_sha256": source_hash, "nodes": nodes})
    _require(ir.get("ir_sha256") == expected_hash, "ConstraintIR fingerprint mismatch")
    summary = ir.get("summary")
    _require(isinstance(summary, dict) and summary.get("total") == len(nodes),
             "ConstraintIR summary inconsistent")
    ids: set[str] = set()
    out: list[dict[str, Any]] = []
    deferred_count = 0
    for node in nodes:
        _require(isinstance(node, dict), "Malformed ConstraintIR node")
        node_id, kind = node.get("node_id"), node.get("kind")
        _require(isinstance(node_id, str) and node_id and node_id not in ids,
                 "Missing or duplicate node identity")
        ids.add(node_id)
        _require(kind in KINDS, "Unrecognized constraint kind")
        provenance = node.get("source")
        review = node.get("review")
        _require(isinstance(provenance, dict)
                 and provenance.get("source_sha256") == source_hash
                 and bool(provenance.get("location"))
                 and bool(provenance.get("quotation_sha256")),
                 "Missing or inconsistent source provenance")
        _require(isinstance(review, dict) and review.get("approved") is True
                 and review.get("authentication") == "UNVERIFIED_REVIEWER_LABEL",
                 "Unexpected reviewer authorization claim")
        status = node.get("status")
        _require(status in ("DEFERRED", "PROJECTION_ONLY", "EVALUABLE"),
                 "Unknown node execution status")
        # Even EVALUABLE means capability is declared, not that a check ran.
        if status != "PROJECTION_ONLY":
            deferred_count += 1
        _require(isinstance(node.get("parameters"), dict),
                 "Missing typed parameters")
        out.append({
            "object_id": f"constraint:{node_id}",
            "kind": "CONSTRAINT_CANDIDATE",
            "constraint_kind": kind,
            "parameters": node["parameters"],
            "execution_posture": status,
            "verification": "UNKNOWN",
            "provenance": provenance,
            "review": review,
        })

    _require(summary.get("deferred_semantic_constraints") ==
             sum(n.get("kind") != "EVIDENCE_PRESENCE" for n in nodes),
             "Invalid deferred constraint summary")
    _require(summary.get("evidence_presence_projections") ==
             sum(n.get("kind") == "EVIDENCE_PRESENCE" for n in nodes),
             "Invalid evidence projection summary")
    _require(summary.get("semantic_constraints_executed") == 0,
             "A candidate compiler cannot certify semantic execution")

    return {
        "schema": KNOWLEDGE_SCHEMA,
        "source_sha256": source_hash,
        "source_constraint_ir_sha256": ir["ir_sha256"],
        "objects": out,
        "verification": "UNKNOWN",
        "admission": "INCONCLUSIVE",
        "scope": "REVIEWED_CANDIDATE_STRUCTURE_ONLY",
        "protected_obligations": [x["object_id"] for x in out],
        "boundary": "Semantic meaning and source authenticity remain unverified. "
                    "This bridge does not execute, infer, or authorize constraints.",
    }


def persist_constraint_ir(store: Any, *, source_id: str, revision: str,
                          ir: dict[str, Any]) -> dict[str, Any]:
    """Atomically persist a reviewed candidate projection into SemanticStore.

    This records source-provided fingerprints but cannot authenticate the source.
    All projected objects are explicitly non-admitted. Nothing is inferred
    from prose; WitnessGraph relationships require separate evidence imports.
    """
    _require(isinstance(source_id, str) and bool(source_id.strip())
             and isinstance(revision, str) and bool(revision.strip()),
             "Source identity and revision required")
    compiled = compile_constraint_ir(ir)
    source_hash = compiled["source_sha256"]
    metadata = {
        "constraint_ir_sha256": compiled["source_constraint_ir_sha256"],
        "assurance": "UNVERIFIED_SOURCE_IDENTITY",
        "kind": "REVIEWED_CONSTRAINT_IR",
    }
    with store.db:
        store.db.execute(
            "INSERT INTO source_versions(source_id, revision, source_sha256, metadata_json) "
            "VALUES (?, ?, ?, ?)",
            (source_id, revision, source_hash,
             __import__("json").dumps(metadata, sort_keys=True, separators=(",", ":"))),
        )
        for item in compiled["objects"]:
            object_id = source_id + ":" + item["object_id"]
            payload = dict(item)
            payload["object_id"] = object_id
            payload["source_constraint_ir_sha256"] = compiled["source_constraint_ir_sha256"]
            payload_hash = digest(payload)
            store.db.execute(
                "INSERT INTO semantic_versions(object_id, revision, source_id, "
                "source_revision, kind, payload_json, payload_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (object_id, revision, source_id, revision,
                 payload["kind"],
                 __import__("json").dumps(payload, sort_keys=True,
                                          ensure_ascii=False, separators=(",", ":")),
                 payload_hash),
            )
    return {
        "source_id": source_id,
        "revision": revision,
        "objects_persisted": len(compiled["objects"]),
        "candidate_only": True,
        "admission": "INCONCLUSIVE",
    }
