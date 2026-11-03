"""Experimental persistence primitives for semantic-store records.

Only source identity, immutable semantic versions, graph edges, and fail-closed
admission *recording* are implemented. No semantic verification is performed.
Do not use receipt recording as proof of correctness or source authenticity.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class Admission:
    status: str
    reason: str
    receipt_hash: str


class SemanticStore:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection
        self.db.execute("PRAGMA foreign_keys = ON")

    def initialize(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS source_versions (
            source_id TEXT NOT NULL,
            revision TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            PRIMARY KEY(source_id, revision)
        );
        CREATE TABLE IF NOT EXISTS semantic_versions (
            object_id TEXT NOT NULL,
            revision TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            PRIMARY KEY(object_id, revision),
            FOREIGN KEY(source_id, source_revision)
                REFERENCES source_versions(source_id, revision)
        );
        CREATE TABLE IF NOT EXISTS semantic_edges (
            edge_id TEXT PRIMARY KEY,
            layer TEXT NOT NULL CHECK(layer IN ('KNOWLEDGE','WITNESS','REGIME')),
            from_id TEXT NOT NULL,
            from_revision TEXT NOT NULL,
            to_id TEXT NOT NULL,
            to_revision TEXT NOT NULL,
            relation TEXT NOT NULL,
            properties_json TEXT NOT NULL,
            FOREIGN KEY(from_id, from_revision)
                REFERENCES semantic_versions(object_id, revision),
            FOREIGN KEY(to_id, to_revision)
                REFERENCES semantic_versions(object_id, revision)
        );
        CREATE TABLE IF NOT EXISTS admission_receipts (
            receipt_hash TEXT PRIMARY KEY,
            object_id TEXT NOT NULL,
            revision TEXT NOT NULL,
            packspec_digest TEXT NOT NULL,
            verdict TEXT NOT NULL CHECK(verdict IN ('ADMIT','REFUSE','INCONCLUSIVE')),
            reason TEXT NOT NULL,
            checks_json TEXT NOT NULL,
            FOREIGN KEY(object_id, revision)
                REFERENCES semantic_versions(object_id, revision)
        );
        """)
        # Physical immutability: reject direct SQL UPDATE/DELETE for all ledger tables.
        # Administrators who can drop triggers remain outside this SQLite trust boundary.
        for table in ("source_versions", "semantic_versions", "semantic_edges",
                      "admission_receipts"):
            for action in ("UPDATE", "DELETE"):
                self.db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} "
                    f"BEFORE {action} ON {table} BEGIN "
                    f"SELECT RAISE(ABORT, 'immutable semantic ledger'); END;"
                )

    def add_source(self, source_id: str, revision: str, source_sha256: str,
                   metadata: dict[str, Any]) -> None:
        if len(source_sha256) != 64 or any(x not in "0123456789abcdef" for x in source_sha256):
            raise ValueError("source_sha256 must be lowercase SHA-256 hex")
        data = canonical_bytes(metadata).decode("utf-8")
        with self.db:
            self.db.execute(
                "INSERT INTO source_versions VALUES(?,?,?,?)",
                (source_id, revision, source_sha256, data))

    def add_object(self, object_id: str, revision: str, source_id: str,
                   source_revision: str, kind: str, payload: dict[str, Any]) -> str:
        if not kind or not isinstance(payload, dict):
            raise ValueError("A non-empty kind and object payload are required")
        h = digest(payload)
        with self.db:
            self.db.execute(
                "INSERT INTO semantic_versions VALUES(?,?,?,?,?,?,?)",
                (object_id, revision, source_id, source_revision, kind,
                 canonical_bytes(payload).decode("utf-8"), h))
        return h

    def add_edge(self, edge_id: str, layer: str, from_id: str, from_revision: str,
                 to_id: str, to_revision: str, relation: str,
                 properties: dict[str, Any] | None = None) -> None:
        with self.db:
            self.db.execute("INSERT INTO semantic_edges VALUES(?,?,?,?,?,?,?,?)",
                            (edge_id, layer, from_id, from_revision, to_id,
                             to_revision, relation,
                             canonical_bytes(properties or {}).decode("utf-8")))

    def object_version(self, object_id: str, revision: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT payload_json FROM semantic_versions WHERE object_id=? AND revision=?",
            (object_id, revision)).fetchone()
        return json.loads(row[0]) if row else None

    def record_admission(self, object_id: str, revision: str, packspec_digest: str,
                         checks: list[dict[str, Any]]) -> Admission:
        """Record check outcomes; cannot manufacture PASS from missing evidence.

        Checks are untrusted *supplied evaluator results*. Only an authenticated
        integration can bind them to a real evaluation. Therefore this method
        deliberately never returns ADMIT. A trusted evaluator integration must
        be added separately with authenticated receipts and verifier identities.
        """
        if not packspec_digest or not isinstance(checks, list):
            raise ValueError("PackSpec digest and checks array are mandatory")
        failed = [c for c in checks if c.get("status") in ("FAIL", "UNSAT")]
        status = "REFUSE" if failed else "INCONCLUSIVE"
        reason = ("Supplied checks include an explicit failure"
                  if failed else "Trusted verifier binding not implemented")
        receipt = {
            "object_id": object_id, "revision": revision,
            "packspec_digest": packspec_digest, "checks": checks,
            "verdict": status, "reason": reason,
        }
        h = digest(receipt)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO admission_receipts VALUES(?,?,?,?,?,?,?)",
                (h, object_id, revision, packspec_digest, status, reason,
                 canonical_bytes(checks).decode("utf-8")))
        return Admission(status, reason, h)
