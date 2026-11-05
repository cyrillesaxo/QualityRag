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
        branches, events, previous, order = {}, {}, None, []
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
            if operation == "CHALLENGE":
                branches[branch].setdefault("challenges", []).append(event_id)
            if operation == "PRUNE":
                branches[branch]["active"] = False
                branches[branch]["pruned_by"] = event_id
            elif operation == "REOPEN":
                branches[branch]["active"] = True
                # Reopening restores the reference context: what pruned it and every prior counterexample.
                branches[branch]["reopened_context"] = {
                    "reopen_event": event_id, "pruned_by": branches[branch].get("pruned_by"),
                    "prior_challenges": list(branches[branch].get("challenges", [])),
                    "parents": list(branches[branch]["parents"])}
            branches[branch]["events"].append(event_id)
            events[event_id] = {**body, "sequence": len(order) + 1}  # 1-based position in the chain
            order.append(event_id)
            previous = event_hash
        # Evidence status is owned by the Research Ledger (which only records VALIDATED through
        # a host-installed verifier); the Gardener reports it and never upgrades it itself.
        statuses = {claim["claim_id"]: claim["effective_status"]
                    for claim in ledger.progress(self.db, project="semantic-gardener")["claims"]}
        for info in branches.values():
            info["evidence_status"] = statuses.get(info["claim_id"], "UNVERIFIED")
        return {"branches": branches, "events": events, "head": previous, "order": order,
                "head_sequence": len(order),
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


QUERY_KEYS = {"text", "evidence_status", "open_challenge", "active", "lineage_of", "depends_on", "since", "limit"}


def _open_challenge(state, info):
    history = [state["events"][eid] for eid in info["events"]]
    last = max((i for i, e in enumerate(history) if e["operation"] == "CHALLENGE"), default=None)
    return last is not None and not any(e["operation"] == "TEST" for e in history[last + 1:])


def query(state, *, text=None, evidence_status=None, open_challenge=None, active=None,
          lineage_of=None, depends_on=None, since=0, limit=200):
    """Read-only query over a replayed garden.

    Filters combine with AND. ``lineage_of`` keeps a branch with its ancestors and descendants.
    ``depends_on`` (an evidence ID or a source SHA-256) keeps the branches whose events cite it,
    plus every descendant: the set to re-check when that witness changes. Each row then says
    whether it depends directly or through an ancestor.
    ``since`` returns the events appended after that sequence number, so a client can follow
    the tree as it grows without reloading it. Nothing here validates a claim.
    """
    if text is not None and (not isinstance(text, str) or len(text) > 200):
        raise ValueError("Bounded text query required")
    if evidence_status is not None and not isinstance(evidence_status, str):
        raise ValueError("Evidence status must be a string")
    for name, value in (("open_challenge", open_challenge), ("active", active)):
        if value is not None and type(value) is not bool:
            raise ValueError(name + " must be a boolean")
    if type(since) is not int or since < 0 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Bounded since/limit required")
    branches = state["branches"]
    children = {name: [] for name in branches}
    for name, info in branches.items():
        for parent in info["parents"]:
            children[parent].append(name)
    keep = None
    if lineage_of is not None:
        if lineage_of not in branches:
            raise ValueError("Unknown branch")
        keep, stack = {lineage_of}, [lineage_of]
        while stack:  # ancestors
            for parent in branches[stack.pop()]["parents"]:
                if parent not in keep:
                    keep.add(parent); stack.append(parent)
        down, stack = set(), [lineage_of]
        while stack:  # descendants
            for child in children[stack.pop()]:
                if child not in down:
                    down.add(child); stack.append(child)
        keep |= down
    impacted = None
    if depends_on is not None:
        if not isinstance(depends_on, str) or not 0 < len(depends_on) <= 200:
            raise ValueError("depends_on must be an evidence ID or source SHA-256")
        direct = {name for name, info in branches.items()
                  if any(depends_on in state["events"][e].get("evidence_ids", []) or
                         state["events"][e]["source_sha256"] == depends_on for e in info["events"])}
        impacted, stack = {n: "direct" for n in direct}, list(direct)
        while stack:
            for child in children[stack.pop()]:
                if child not in impacted:
                    impacted[child] = "inherited"; stack.append(child)
    needle = text.casefold().strip() if text else None
    rows = []
    for name, info in branches.items():
        history = [state["events"][eid] for eid in info["events"]]
        opened = _open_challenge(state, info)
        if keep is not None and name not in keep:
            continue
        if impacted is not None and name not in impacted:
            continue
        if evidence_status is not None and info["evidence_status"] != evidence_status:
            continue
        if open_challenge is not None and opened != open_challenge:
            continue
        if active is not None and info["active"] != active:
            continue
        if needle and needle not in (name + " " + " ".join(e["statement"] for e in history)).casefold():
            continue
        first = history[0]
        rows.append({"branch": name, "statement": first["statement"], "active": info["active"],
                     "evidence_status": info["evidence_status"], "parents": list(info["parents"]),
                     "children": sorted(children[name]), "open_challenge": opened,
                     "events": len(history), "created_sequence": first["sequence"],
                     "last_sequence": history[-1]["sequence"], "source_ref": first["source_ref"],
                     "source_sha256": first["source_sha256"],
                     **({"dependency": impacted[name]} if impacted is not None else {})})
    rows.sort(key=lambda r: r["created_sequence"])
    new_events = [state["events"][eid] for eid in state["order"][since:since + 500]]
    return {"schema": "qualityrag.gardener-query/v1", "branches": rows[:limit], "total": len(rows),
            "truncated": len(rows) > limit, "events": new_events, "since": since,
            "head_sequence": state["head_sequence"], "events_truncated": state["head_sequence"] - since > 500,
            "independent_validation": "NOT_ESTABLISHED"}

