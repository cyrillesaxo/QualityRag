"""Governed conversation tree: custody, node PackSpecs, drift fork, ledger and read-back gate.

Implements the first slice of EPIC E11 (docs/FR-E11-GOVERNED-CONVERSATION-TREE.md):
US-069 to US-073, part of US-075, US-076, US-077 and US-079. Later stories live in the sibling
modules: differential (US-074), compaction (US-078), lake (US-080), retrieval (US-081),
mcp_server (US-082), receipts (US-083) and evaluation (US-084 harness).

Everything is deterministic and local. No model is called. Nothing here validates
meaning: obligations are lexical candidates, the classifier is unmeasured, and the
strongest verdict is COMPLETE_WITHIN_SCOPE with can_generate false.

Hashes and triggers detect ordinary corruption; a database administrator can still
rewrite local state. The event chain follows the Gardener pattern (US-034/035) but is
a separate chain, because Gardener.append records every new branch as a research
HYPOTHESIS in the Research Ledger, which a conversation branch is not.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import sqlite3

from tools.activation_runtime.common import canonical, fingerprint, identity

from .classify import classify
from .triggers import CRITICAL_FAMILIES, TRIGGER_SET, scan

SCHEMA = "qualityrag.conversation-tree/v0.1"
PACKSPEC_SCHEMA = "qualityrag.conversation-node-packspec/v0.1"
ACTORS = frozenset(("USER", "ASSISTANT", "TOOL", "SYSTEM"))
DISPOSITIONS = ("REPRESENTED", "RESIDUAL", "EXCLUDED_BY_RULE", "UNKNOWN")
MAX_TURN_BYTES = 1_048_576
MAX_TURN_ID = 48
DEFAULT_LIVE_BRANCH_CAP = 8


class BranchBudgetExceeded(ValueError):
    """The live-branch cap is reached; the caller must ask the user which branch to close."""


def _at(value):
    if not isinstance(value, str) or datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return value


def _decode(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


class ConversationTree:
    def __init__(self, path, *, live_branch_cap=DEFAULT_LIVE_BRANCH_CAP):
        if type(live_branch_cap) is not int or not 2 <= live_branch_cap <= 64:
            raise ValueError("Invalid live-branch cap")
        self.cap = live_branch_cap
        self.db = sqlite3.connect(path, timeout=5)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS conversation_turns(
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            turn_id TEXT NOT NULL UNIQUE,
            actor TEXT NOT NULL,
            at TEXT NOT NULL,
            content BLOB NOT NULL,
            content_sha256 TEXT NOT NULL,
            previous TEXT,
            turn_hash TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS conversation_events(
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            event_hash TEXT NOT NULL UNIQUE
        );
        CREATE TRIGGER IF NOT EXISTS conversation_turns_no_update BEFORE UPDATE ON conversation_turns
          BEGIN SELECT RAISE(ABORT,'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS conversation_turns_no_delete BEFORE DELETE ON conversation_turns
          BEGIN SELECT RAISE(ABORT,'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS conversation_events_no_update BEFORE UPDATE ON conversation_events
          BEGIN SELECT RAISE(ABORT,'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS conversation_events_no_delete BEFORE DELETE ON conversation_events
          BEGIN SELECT RAISE(ABORT,'append-only'); END;
        """)

    def close(self):
        self.db.close()

    # ------------------------------------------------------------------ custody (US-069)

    def append_turn(self, *, turn_id, actor, content, at):
        identity(turn_id)
        if len(turn_id) > MAX_TURN_ID or actor not in ACTORS:
            raise ValueError("Invalid turn identifier or actor class")
        raw = content.encode("utf-8") if isinstance(content, str) else content
        if not isinstance(raw, bytes) or len(raw) > MAX_TURN_BYTES:
            raise ValueError("Bounded turn content required")
        _at(at)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT turn_hash FROM conversation_turns ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = row[0] if row else None
            digest = sha256(raw).hexdigest()
            turn_hash = fingerprint({"turn_id": turn_id, "actor": actor, "at": at,
                                     "content_sha256": digest, "previous": previous})
            self.db.execute(
                "INSERT INTO conversation_turns(turn_id,actor,at,content,content_sha256,previous,turn_hash)"
                " VALUES(?,?,?,?,?,?,?)", (turn_id, actor, at, raw, digest, previous, turn_hash))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"turn_id": turn_id, "actor": actor, "content_sha256": digest, "turn_hash": turn_hash}

    def turns(self):
        """Verified turns in order. Any altered, missing or reordered turn raises; nothing is repaired."""
        out, previous, expected = [], None, None
        for sequence, turn_id, actor, at, raw, digest, prev, turn_hash in self.db.execute(
                "SELECT sequence,turn_id,actor,at,content,content_sha256,previous,turn_hash"
                " FROM conversation_turns ORDER BY sequence"):
            raw = bytes(raw)
            if expected is not None and sequence != expected:
                raise ValueError("Turn custody corruption: sequence gap")
            if (prev != previous or sha256(raw).hexdigest() != digest or actor not in ACTORS
                    or fingerprint({"turn_id": turn_id, "actor": actor, "at": at,
                                    "content_sha256": digest, "previous": prev}) != turn_hash):
                raise ValueError("Turn custody corruption")
            out.append({"sequence": sequence, "turn_id": turn_id, "actor": actor, "at": at,
                        "content": raw, "content_sha256": digest, "turn_hash": turn_hash})
            previous, expected = turn_hash, sequence + 1
        return out

    def custody_report(self):
        turns = self.turns()
        return {"schema": SCHEMA, "turns": len(turns), "bytes": sum(len(t["content"]) for t in turns),
                "head": turns[-1]["turn_hash"] if turns else None,
                "reconstruction": "BYTE_EXACT", "semantic_coverage": "NONE_CLAIMED"}

    # ------------------------------------------------------------------ event chain

    def _events(self):
        out, previous = [], None
        for sequence, body_raw, event_hash in self.db.execute(
                "SELECT sequence,body,event_hash FROM conversation_events ORDER BY sequence"):
            body = json.loads(body_raw)
            if body.get("previous") != previous or fingerprint(body) != event_hash:
                raise ValueError("Conversation event-chain corruption")
            out.append({**body, "sequence": sequence, "event_hash": event_hash})
            previous = event_hash
        return out

    def _append(self, kind, at, data):
        """Append inside the caller's transaction; returns the new event ID."""
        row = self.db.execute(
            "SELECT sequence,event_hash FROM conversation_events ORDER BY sequence DESC LIMIT 1").fetchone()
        event_id = "e%06d" % ((row[0] if row else 0) + 1)
        body = {"event_id": event_id, "kind": kind, "at": _at(at), "data": data,
                "previous": row[1] if row else None}
        self.db.execute("INSERT INTO conversation_events(body,event_hash) VALUES(?,?)",
                        (canonical(body).decode(), fingerprint(body)))
        return event_id

    def _write(self, operation):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = operation(self.replay())
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return result

    def replay(self):
        """Rebuild the tree deterministically from custody and the event chain."""
        turns = {t["turn_id"]: t for t in self.turns()}
        branches, classifications, differentials, standing, head = {}, [], [], [], None
        for event in self._events():
            kind, data, eid = event["kind"], event["data"], event["event_id"]
            head = event["event_hash"]
            if kind == "BRANCH":
                name, parent = data["branch"], data["parent"]
                if name in branches or (parent is not None and parent not in branches):
                    raise ValueError("Invalid branch ancestry")
                branches[name] = {"kind": data["kind"], "parent": parent,
                                  "parent_upto": data["parent_upto"], "fork_id": data["fork_id"],
                                  "created_by": eid, "active": True, "members": [],
                                  "packspecs": [], "superseded": {}, "confirmed": {},
                                  "history": []}
                continue
            if kind == "CLASSIFY":
                classifications.append({**data, "event_id": eid})
                continue
            if kind == "DIFFERENTIAL":
                differentials.append({**data, "event_id": eid})
                continue
            if kind == "STANDING":
                if data["turn_id"] not in turns:
                    raise ValueError("Event references a turn missing from custody")
                standing.append({**data, "event_id": eid})
                continue
            branch = branches.get(data.get("branch"))
            if branch is None:
                raise ValueError("Event for unknown branch")
            if data.get("turn_id") is not None and data["turn_id"] not in turns:
                raise ValueError("Event references a turn missing from custody")
            if kind == "ATTACH":
                branch["members"].append(data["turn_id"])
            elif kind == "GOVERN":
                branch["packspecs"].append({**data["packspec"], "event_id": eid})
            elif kind == "SUPERSEDE":
                branch["superseded"][data["obligation_id"]] = eid
            elif kind == "CONFIRM":
                branch["confirmed"][data["turn_id"]] = {"by": data["by_turn"], "event_id": eid}
            elif kind == "PRUNE":
                branch["active"], branch["pruned_by"] = False, eid
            elif kind == "REOPEN":
                branch["active"] = True
                branch["reopened_context"] = {"reopen_event": eid, "pruned_by": branch.get("pruned_by")}
            else:
                raise ValueError("Unknown event kind")
            branch["history"].append(eid)
        return {"schema": SCHEMA, "turns": turns, "branches": branches,
                "classifications": classifications, "differentials": differentials, "standing": standing, "head": head,
                "independent_validation": "NOT_ESTABLISHED"}

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _effective(state, name):
        """Turn IDs visible on a branch: inherited context up to the fork, then its own members."""
        branch = state["branches"][name]
        inherited = []
        if branch["kind"] == "MERGED":
            inherited = ConversationTree._effective(state, branch["parent"])[:branch["parent_upto"]]
        return inherited + branch["members"]

    @staticmethod
    def _scope(state, name):
        """Standing rules above the tree, then the branch's own visible turns."""
        return [s["turn_id"] for s in state["standing"]] + ConversationTree._effective(state, name)

    def visible_turns(self, branch):
        """Turn IDs in scope for a branch, in order: standing rules first, then the branch context."""
        state = self.replay()
        if branch not in state["branches"]:
            raise ValueError("Unknown branch")
        return self._scope(state, branch)

    @staticmethod
    def _candidates(turn):
        """Lexical obligation candidates from one USER turn. Not reviewed, not complete."""
        text = _decode(turn["content"])
        if text is None:
            return None
        out = []
        for span in scan(text):
            if span["families"]:
                out.append({"obligation_id": "ob-%s-%d-%d" % (turn["turn_id"], span["start"], span["end"]),
                            "turn_id": turn["turn_id"], "start": span["start"], "end": span["end"],
                            "families": span["families"],
                            "critical": bool(CRITICAL_FAMILIES.intersection(span["families"])),
                            "quote_sha256": sha256(text[span["start"]:span["end"]].encode()).hexdigest(),
                            "origin": "TRIGGER", "review": "UNREVIEWED"})
        return out

    def _packspec(self, state, name, *, version, status, governing, base=(), parent=None):
        """Node PackSpec: obligations inherited from a parent node (``base``) plus this node's own turns."""
        own, unreadable = [], False
        for turn_id in governing:
            found = self._candidates(state["turns"][turn_id])
            if found is None:
                unreadable = True
            else:
                own.extend(found)
        obligations = list(base) + own
        return {"schema": PACKSPEC_SCHEMA, "branch": name, "version": version, "status": status,
                "governing_turns": list(governing), "obligations": obligations,
                # An unreadable turn or an empty inventory is recorded as unknown, never as "no constraints".
                "unknown": unreadable or not obligations,
                "parent_packspec": parent, "trigger_set": TRIGGER_SET,
                "domain_admission": "INCONCLUSIVE"}

    @staticmethod
    def _require_user(state, turn_id):
        turn = state["turns"].get(turn_id)
        if turn is None:
            raise ValueError("Turn missing from custody")
        if turn["actor"] != "USER":
            raise ValueError("Only a USER turn can govern, confirm, supersede or witness")
        return turn

    @staticmethod
    def _live(state, name):
        branch = state["branches"].get(name)
        if branch is None or not branch["active"]:
            raise ValueError("Unknown or inactive branch")
        return branch

    @staticmethod
    def _placed(state, turn_id):
        return (any(turn_id in b["members"] for b in state["branches"].values())
                or any(turn_id == s["turn_id"] for s in state["standing"]))

    def _new_branch(self, state, at, *, name, kind, parent, turn_id, fork_id):
        identity(name)
        if name in state["branches"]:
            raise ValueError("Duplicate branch")
        merged = kind == "MERGED"
        source = state["branches"][parent] if merged else None
        upto = len(self._effective(state, parent)) if merged else 0
        self._append("BRANCH", at, {"branch": name, "kind": kind, "parent": parent,
                                    "parent_upto": upto, "fork_id": fork_id})
        self._append("ATTACH", at, {"branch": name, "turn_id": turn_id})
        inherited = source["packspecs"][-1] if merged else None
        spec = self._packspec(
            state, name, version=1, status="PROVISIONAL", governing=[turn_id],
            base=inherited["obligations"] if merged else (),
            parent={"branch": parent, "version": inherited["version"]} if merged else None)
        self._append("GOVERN", at, {"branch": name, "turn_id": turn_id, "packspec": spec})
        if merged:  # the merged reading keeps the parent's retirements and user confirmations
            for obligation_id, event_id in source["superseded"].items():
                self._append("SUPERSEDE", at, {"branch": name, "obligation_id": obligation_id,
                                               "turn_id": None, "inherited_from": event_id})
            for confirmed, info in source["confirmed"].items():
                self._append("CONFIRM", at, {"branch": name, "turn_id": confirmed,
                                             "by_turn": info["by"], "inherited_from": info["event_id"]})

    # ------------------------------------------------------------------ standing rules (US-070 criterion 4)

    def add_standing_rule(self, *, turn_id, level, at):
        """Place a rule above the tree. It applies to every branch, isolated ones included.

        OPERATOR rules come from a SYSTEM turn, USER-level rules from a USER turn. No node
        can amend, supersede or prune a standing rule; there is deliberately no API for it.
        """
        def operation(state):
            turn = state["turns"].get(turn_id)
            wanted = {"OPERATOR": "SYSTEM", "USER": "USER"}.get(level)
            if turn is None or wanted is None or turn["actor"] != wanted:
                raise ValueError("OPERATOR rules need a SYSTEM turn; USER rules need a USER turn")
            if self._placed(state, turn_id):
                raise ValueError("Turn already placed")
            self._append("STANDING", at, {"turn_id": turn_id, "level": level})
        self._write(operation)
        return self.replay()

    # ------------------------------------------------------------------ governance (US-070/071)

    def open_root(self, *, turn_id, at, branch="root"):
        """The first USER prompt becomes the provisional governance of the conversation."""
        def operation(state):
            if state["branches"]:
                raise ValueError("Root already exists")
            self._require_user(state, turn_id)
            if self._placed(state, turn_id):
                raise ValueError("Turn already placed")
            self._new_branch(state, at, name=branch, kind="ROOT", parent=None,
                             turn_id=turn_id, fork_id=None)
        self._write(operation)
        return self.replay()

    def attach(self, *, branch, turn_id, at):
        """Place an ASSISTANT, TOOL or SYSTEM turn on a branch as evidence. It never governs."""
        def operation(state):
            self._live(state, branch)
            turn = state["turns"].get(turn_id)
            if turn is None or self._placed(state, turn_id):
                raise ValueError("Turn missing from custody or already placed")
            if turn["actor"] == "USER":
                raise ValueError("USER turns enter through advance(), which classifies them")
            self._append("ATTACH", at, {"branch": branch, "turn_id": turn_id})
        self._write(operation)
        return self.replay()

    def set_status(self, *, branch, status, by_turn, at):
        """A user promotes a node to governance or returns it to provisional. Attributed, append-only."""
        def operation(state):
            node = self._live(state, branch)
            self._require_user(state, by_turn)
            if status not in ("PROMOTED", "PROVISIONAL"):
                raise ValueError("Invalid status")
            current = node["packspecs"][-1]
            spec = {k: v for k, v in current.items() if k != "event_id"}
            spec.update(version=current["version"] + 1, status=status)
            self._append("GOVERN", at, {"branch": branch, "turn_id": by_turn, "packspec": spec})
        self._write(operation)
        return self.replay()

    def confirm(self, *, branch, turn_id, by_turn, at):
        """Admit an ASSISTANT or TOOL turn into node state. Requires a later USER turn on the branch."""
        def operation(state):
            self._live(state, branch)
            visible = self._effective(state, branch)
            target, witness = state["turns"].get(turn_id), self._require_user(state, by_turn)
            if target is None or target["actor"] not in ("ASSISTANT", "TOOL"):
                raise ValueError("Only ASSISTANT or TOOL evidence is confirmed")
            if turn_id not in visible or by_turn not in visible or witness["sequence"] <= target["sequence"]:
                raise ValueError("Confirmation needs a later USER turn on the same branch")
            self._append("CONFIRM", at, {"branch": branch, "turn_id": turn_id, "by_turn": by_turn})
        self._write(operation)
        return self.replay()

    def supersede(self, *, branch, obligation_id, by_turn, at):
        """A later USER turn retires an obligation. The old span stays in custody and in the ledger."""
        def operation(state):
            node = self._live(state, branch)
            witness = self._require_user(state, by_turn)
            match = [o for o in node["packspecs"][-1]["obligations"] if o["obligation_id"] == obligation_id]
            if not match or obligation_id in node["superseded"]:
                raise ValueError("Unknown or already superseded obligation")
            if (by_turn not in self._effective(state, branch)
                    or witness["sequence"] <= state["turns"][match[0]["turn_id"]]["sequence"]):
                raise ValueError("Supersession needs a later USER turn on the same branch")
            self._append("SUPERSEDE", at, {"branch": branch, "obligation_id": obligation_id,
                                           "turn_id": by_turn})
        self._write(operation)
        return self.replay()

    # ------------------------------------------------------------------ drift fork (US-072/073)

    def _context_text(self, state, name):
        """User-authored text of a branch. Assistant text does not steer classification."""
        parts = []
        for turn_id in self._effective(state, name):
            turn = state["turns"][turn_id]
            text = _decode(turn["content"]) if turn["actor"] == "USER" else None
            if text:
                parts.append(text)
        return "\n".join(parts)

    def advance(self, *, branch, turn_id, at, fork_id=None):
        """Place a new USER turn: REFINE amends, AMBIGUOUS forks twice, PIVOT isolates."""
        def operation(state):
            node = self._live(state, branch)
            turn = self._require_user(state, turn_id)
            if self._placed(state, turn_id):
                raise ValueError("Turn already placed")
            text = _decode(turn["content"])
            result = classify(text, self._context_text(state, branch))  # non-text input fails to fork
            self._append("CLASSIFY", at, {"branch": branch, "turn_id": turn_id,
                                          "verdict": result["verdict"], "features": result["features"],
                                          "classifier": result["classifier"],
                                          "thresholds": result["thresholds"]})
            current = node["packspecs"][-1]
            if result["verdict"] == "REFINE":
                self._append("ATTACH", at, {"branch": branch, "turn_id": turn_id})
                own = set(current["governing_turns"])
                spec = self._packspec(
                    state, branch, version=current["version"] + 1, status=current["status"],
                    governing=current["governing_turns"] + [turn_id],
                    # Obligations inherited from a parent node stay; this node's own turns are rescanned.
                    base=[o for o in current["obligations"] if o["turn_id"] not in own],
                    parent=current["parent_packspec"])
                self._append("GOVERN", at, {"branch": branch, "turn_id": turn_id, "packspec": spec})
                return {"verdict": "REFINE", "branches": [branch]}
            fork = identity(fork_id or "f-" + turn_id)
            created = [fork + "-iso"] + ([fork + "-mrg"] if result["verdict"] == "AMBIGUOUS" else [])
            live = sum(1 for b in state["branches"].values() if b["active"])
            if live + len(created) > self.cap:
                raise BranchBudgetExceeded(
                    "Live-branch cap %d reached; ask the user which branch to close" % self.cap)
            self._new_branch(state, at, name=created[0], kind="ISOLATED", parent=branch,
                             turn_id=turn_id, fork_id=fork)
            if len(created) == 2:
                self._new_branch(state, at, name=created[1], kind="MERGED", parent=branch,
                                 turn_id=turn_id, fork_id=fork)
            return {"verdict": result["verdict"], "branches": created}
        result = self._write(operation)
        return {**result, "state": self.replay()}

    # ------------------------------------------------------------------ collapse (US-075, partial)

    def prune(self, *, branch, witness_turn, reason, at):
        """Close a branch on the evidence of a USER turn. Nothing is deleted."""
        def operation(state):
            self._live(state, branch)
            self._require_user(state, witness_turn)
            if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
                raise ValueError("Bounded reason required")
            self._append("PRUNE", at, {"branch": branch, "turn_id": witness_turn, "reason": reason.strip()})
        self._write(operation)
        return self.replay()

    def reopen(self, *, branch, witness_turn, at):
        def operation(state):
            node = state["branches"].get(branch)
            if node is None or node["active"]:
                raise ValueError("Only a pruned branch can be reopened")
            self._require_user(state, witness_turn)
            if sum(1 for b in state["branches"].values() if b["active"]) + 1 > self.cap:
                raise BranchBudgetExceeded("Live-branch cap %d reached" % self.cap)
            self._append("REOPEN", at, {"branch": branch, "turn_id": witness_turn})
        self._write(operation)
        return self.replay()

    # ------------------------------------------------------------------ differential test (US-074)

    def record_differential(self, *, fork_id, isolated, merged, at):
        """Compare the answers of the two fork branches and act on the result.

        The caller runs both branches; this records the comparison. AGREE means the earlier
        context did not change the declared decisions, so the isolated branch is closed (the
        merged branch keeps the governance and loses nothing). DIVERGE and UNKNOWN close nothing
        and return the differences for the user. Closing is reversible with reopen().
        """
        from .differential import compare
        result = compare(isolated, merged)

        def operation(state):
            names = (fork_id + "-iso", fork_id + "-mrg")
            if isolated.get("branch") != names[0] or merged.get("branch") != names[1]:
                raise ValueError("Answers must come from the two branches of this fork")
            for name in names:
                node = self._live(state, name)
                if node["fork_id"] != fork_id:
                    raise ValueError("Branch does not belong to this fork")
            if any(d["fork_id"] == fork_id for d in state["differentials"]):
                raise ValueError("Fork already compared")
            event = self._append("DIFFERENTIAL", at, {"fork_id": fork_id, **result})
            if result["handled_as"] == "AGREE":
                self._append("PRUNE", at, {"branch": names[0], "turn_id": None,
                                           "reason": "DIFFERENTIAL_AGREE: earlier context not load-bearing",
                                           "by_event": event})
            return event
        event = self._write(operation)
        return {**result, "event_id": event, "state": self.replay()}

    # ------------------------------------------------------------------ ledger (US-076)

    def ledger(self, branch):
        """Every span of every turn in custody gets exactly one disposition for this branch."""
        state = self.replay()
        node = state["branches"].get(branch)
        if node is None:
            raise ValueError("Unknown branch")
        visible = set(self._effective(state, branch))
        standing = {s["turn_id"]: s["event_id"] for s in state["standing"]}
        spec = node["packspecs"][-1]
        obligations = {(o["turn_id"], o["start"], o["end"]): o for o in spec["obligations"]}
        spans, counts, chars = [], dict.fromkeys(DISPOSITIONS, 0), dict.fromkeys(DISPOSITIONS, 0)

        def record(turn, start, end, disposition, rule=None, cites=None, obligation=None):
            spans.append({"turn_id": turn["turn_id"], "actor": turn["actor"], "start": start, "end": end,
                          "disposition": disposition, "rule": rule, "cites": cites,
                          "obligation_id": obligation})
            counts[disposition] += 1
            chars[disposition] += end - start

        for turn in sorted(state["turns"].values(), key=lambda t: t["sequence"]):
            text = _decode(turn["content"])
            if text is None:
                record(turn, 0, len(turn["content"]), "UNKNOWN", rule="NOT_UTF8_TEXT")
                continue
            placed = self._placed(state, turn["turn_id"])
            for item in scan(text):
                start, end = item["start"], item["end"]
                if turn["turn_id"] in standing:
                    record(turn, start, end, "REPRESENTED", rule="STANDING_RULE",
                           cites=standing[turn["turn_id"]],
                           obligation="st-%s-%d-%d" % (turn["turn_id"], start, end))
                    continue
                if turn["turn_id"] not in visible:
                    if placed:
                        record(turn, start, end, "EXCLUDED_BY_RULE", rule="OUT_OF_BRANCH_SCOPE",
                               cites=node["created_by"])
                    else:
                        record(turn, start, end, "UNKNOWN", rule="TURN_NOT_PLACED")
                    continue
                found = obligations.get((turn["turn_id"], start, end))
                if found is not None:
                    retired = node["superseded"].get(found["obligation_id"])
                    if retired:
                        record(turn, start, end, "EXCLUDED_BY_RULE", rule="SUPERSEDED", cites=retired,
                               obligation=found["obligation_id"])
                    else:
                        record(turn, start, end, "REPRESENTED", obligation=found["obligation_id"])
                elif turn["turn_id"] in node["confirmed"]:
                    record(turn, start, end, "REPRESENTED", rule="EVIDENCE_CONFIRMED_BY_USER",
                           cites=node["confirmed"][turn["turn_id"]]["event_id"])
                else:
                    record(turn, start, end, "RESIDUAL")

        # Conservation: per turn, spans are contiguous from 0 to the end with no gap or overlap.
        position = {}
        for span in spans:
            if span["start"] != position.get(span["turn_id"], 0) or span["end"] <= span["start"]:
                raise ValueError("Span conservation violated")
            position[span["turn_id"]] = span["end"]
        for turn in state["turns"].values():
            text = _decode(turn["content"])
            if position.get(turn["turn_id"], 0) != (len(turn["content"]) if text is None else len(text)):
                raise ValueError("Span conservation violated")
        in_scope = chars["REPRESENTED"] + chars["RESIDUAL"]
        return {"schema": SCHEMA, "branch": branch, "packspec_version": spec["version"],
                "trigger_set": TRIGGER_SET, "snapshot": state["head"], "offset_unit": "utf8-char",
                "spans": spans, "counts": counts, "chars": chars,
                # Storing everything as residual is legal and earns no coverage.
                "admitted_coverage": (chars["REPRESENTED"] / in_scope) if in_scope else 0.0,
                "obligation_inventory": "LEXICAL_CANDIDATES_INCOMPLETE"}

    # ------------------------------------------------------------------ read-back gate (US-079)

    def gate(self, branch, *, loaded):
        """Decide from the ledger, not from model discretion, what must be read before answering.

        ``loaded`` is the set of turn IDs the assistant currently holds verbatim. The verdict
        never exceeds COMPLETE_WITHIN_SCOPE and never permits generation by itself.
        """
        state = self.replay()
        node = state["branches"].get(branch)
        if node is None or not node["active"]:
            raise ValueError("Unknown or inactive branch")
        loaded = set(loaded)
        if not all(isinstance(t, str) for t in loaded):
            raise ValueError("Loaded turn IDs must be strings")
        spec = node["packspecs"][-1]
        rows, required = [], []
        for item in spec["obligations"]:
            if item["obligation_id"] in node["superseded"]:
                status = "NOT_APPLICABLE"
            elif item["turn_id"] in loaded:
                status = "SUPPORTED"
            else:
                status = "UNSUPPORTED"
                if item["critical"]:
                    required.append({"obligation_id": item["obligation_id"], "turn_id": item["turn_id"],
                                     "start": item["start"], "end": item["end"]})
            rows.append({"obligation_id": item["obligation_id"], "critical": item["critical"],
                         "status": status})
        unknown = spec["unknown"]
        for rule in state["standing"]:  # every span of a standing rule is a critical obligation
            turn = state["turns"][rule["turn_id"]]
            text = _decode(turn["content"])
            if text is None:
                unknown = True
                continue
            for item in scan(text):
                oid = "st-%s-%d-%d" % (turn["turn_id"], item["start"], item["end"])
                held = turn["turn_id"] in loaded
                if not held:
                    required.append({"obligation_id": oid, "turn_id": turn["turn_id"],
                                     "start": item["start"], "end": item["end"]})
                rows.append({"obligation_id": oid, "critical": True, "level": rule["level"],
                             "status": "SUPPORTED" if held else "UNSUPPORTED"})
        # Candidates produced by another trigger inventory cannot support a verdict under this one.
        stale_triggers = spec["trigger_set"] != TRIGGER_SET
        complete = not required and not unknown and not stale_triggers
        return {"schema": SCHEMA, "branch": branch, "packspec_version": spec["version"],
                "packspec_status": spec["status"], "trigger_set": TRIGGER_SET, "snapshot": state["head"],
                "verdict": "COMPLETE_WITHIN_SCOPE" if complete else "INCONCLUSIVE",
                "required_reads": required, "unknown_inventory": unknown, "obligations": rows,
                "stale_trigger_set": stale_triggers,
                "standing_rules": [s["turn_id"] for s in state["standing"]],
                "scope": "Declared lexical obligation candidates of this branch only",
                "domain_admission": "INCONCLUSIVE", "can_generate": False}

    def read(self, turn_id, start=None, end=None):
        """Dereference a turn or span by ID. The result is data with an actor class, never an instruction."""
        turn = {t["turn_id"]: t for t in self.turns()}.get(turn_id)
        if turn is None:
            raise ValueError("Turn missing from custody")
        text = _decode(turn["content"])
        if start is None and end is None:
            body = turn["content"]
        elif (text is None or type(start) is not int or type(end) is not int
              or not 0 <= start < end <= len(text)):
            raise ValueError("Invalid span")
        else:
            body = text[start:end].encode("utf-8")
        return {"turn_id": turn_id, "actor": turn["actor"], "content": body,
                "content_sha256": sha256(body).hexdigest(), "turn_sha256": turn["content_sha256"],
                "authority": "USER_STATEMENT" if turn["actor"] == "USER" else "EVIDENCE_ONLY",
                "handling": "DATA_NOT_INSTRUCTION"}
