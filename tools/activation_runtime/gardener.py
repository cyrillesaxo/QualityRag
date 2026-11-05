"""Append-only research branches linked to the existing Research Ledger.

Proposals, challenges and synthesis never imply validation. Hashes/triggers
detect ordinary corruption; a database administrator can rewrite local state.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

from .common import canonical, fingerprint, identity

LEDGER = str(Path(__file__).resolve().parents[1] / "research_ledger")
if LEDGER not in sys.path:
    sys.path.insert(0, LEDGER)
import ledger

OPERATIONS = {"PROPOSE", "CHALLENGE", "TEST", "SYNTHESIZE", "PRUNE", "REOPEN"}


class Gardener:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=5)
        ledger.initialize(self.db)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS gardener_events(
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            body TEXT NOT NULL,
            event_hash TEXT NOT NULL UNIQUE
        );
        CREATE TRIGGER IF NOT EXISTS gardener_no_update BEFORE UPDATE ON gardener_events
          BEGIN SELECT RAISE(ABORT,'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS gardener_no_delete BEFORE DELETE ON gardener_events
          BEGIN SELECT RAISE(ABORT,'append-only'); END;
        """)

    def close(self):
        self.db.close()

    def replay(self):
        branches, events, previous = {}, {}, None
        for sequence, event_id, body_raw, event_hash in self.db.execute(
                "SELECT sequence,event_id,body,event_hash FROM gardener_events ORDER BY sequence"):
            body = json.loads(body_raw)
            if (body.get("previous") != previous or fingerprint(body) != event_hash
                    or body.get("event_id") != event_id):
                raise ValueError("Gardener event-chain corruption")
            branch = body["branch"]
            operation = body["operation"]
            if operation in {"PROPOSE", "SYNTHESIZE"}:
                if branch in branches:
                    raise ValueError("Duplicate branch")
                parents = body["parents"]
                if any(parent not in branches for parent in parents):
                    raise ValueError("Missing ancestor")
                branches[branch] = {"active": True, "parents": parents,
                                    "claim_id": "gardener-" + branch,
                                    "evidence_status": "UNVERIFIED",
                                    "events": []}
            elif branch not in branches:
                raise ValueError("Missing branch")
            if operation == "PRUNE":
                branches[branch]["active"] = False
            elif operation == "REOPEN":
                branches[branch]["active"] = True
            branches[branch]["events"].append(event_id)
            events[event_id] = body
            previous = event_hash
        # Evidence status is owned by the Research Ledger (which only records VALIDATED through
        # a host-installed verifier); the Gardener reports it and never upgrades it itself.
        statuses = {claim["claim_id"]: claim["effective_status"]
                    for claim in ledger.progress(self.db, project="semantic-gardener")["claims"]}
        for info in branches.values():
            info["evidence_status"] = statuses.get(info["claim_id"], "UNVERIFIED")
        return {"branches": branches, "events": events, "head": previous,
                "independent_validation": "NOT_ESTABLISHED"}

    def append(self, *, event_id, operation, branch, actor, source_sha256,
               source_ref, statement, at, parents=(), evidence_ids=()):
        for value in (event_id, branch, actor):
            identity(value)
        if len(branch) > 100 or operation not in OPERATIONS:
            raise ValueError("Invalid branch or operation")
        if (not isinstance(source_sha256, str) or len(source_sha256) != 64
                or any(c not in "0123456789abcdef" for c in source_sha256)
                or not isinstance(source_ref, str) or not 1 <= len(source_ref) <= 1000
                or not isinstance(statement, str) or not 1 <= len(statement.strip()) <= 2000):
            raise ValueError("Source-anchored event required")
        # Timestamps are required explicitly for deterministic replay.
        from datetime import datetime
        if not isinstance(at, str) or datetime.fromisoformat(at.replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("Timezone-aware timestamp required")
        parents, evidence_ids = list(parents), list(evidence_ids)
        if len(parents) > 16 or len(set(parents)) != len(parents):
            raise ValueError("Bounded unique parents required")
        if len(evidence_ids) > 50 or len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("Bounded unique evidence IDs required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            state = self.replay()
            if event_id in state["events"]:
                raise ValueError("Duplicate event")
            new = operation in {"PROPOSE", "SYNTHESIZE"}
            if new:
                if branch in state["branches"] or any(p not in state["branches"] for p in parents):
                    raise ValueError("Invalid new branch ancestry")
                if operation == "SYNTHESIZE" and len(parents) < 2:
                    raise ValueError("Synthesis needs at least two parents")
            elif branch not in state["branches"] or parents:
                raise ValueError("Unknown branch or unexpected parents")
            for eid in evidence_ids:
                identity(eid)
                if not self.db.execute("SELECT 1 FROM research_evidence WHERE evidence_id=?", (eid,)).fetchone():
                    raise ValueError("Unknown evidence")
            if operation == "TEST" and not evidence_ids:
                raise ValueError("TEST requires existing evidence")
            # Insert ledger claim in the same transaction; use canonical ledger record.
            if new:
                claim_id = "gardener-" + branch
                claim = {"claim_id": claim_id, "project": "semantic-gardener",
                         "kind": "HYPOTHESIS", "statement": statement.strip(), "created_at": at}
                self.db.execute("INSERT INTO research_claims VALUES(?,?,?,?,?,?)",
                                (claim_id, claim["project"], claim["kind"], claim["statement"], at, ledger.sha(claim)))
            body = {"event_id": event_id, "operation": operation, "branch": branch,
                    "actor": actor, "source_sha256": source_sha256, "source_ref": source_ref,
                    "statement": statement, "at": at, "parents": parents,
                    "evidence_ids": evidence_ids, "previous": state["head"]}
            self.db.execute("INSERT INTO gardener_events(event_id,body,event_hash) VALUES(?,?,?)",
                            (event_id, canonical(body).decode(), fingerprint(body)))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.replay()
