"""Addressable retrieval with a coverage receipt (US-081).

The span index is a derived artifact: it is rebuilt from custody and the event chain and can
be dropped at any time. Every search answers with a receipt that says what was in scope,
what was returned and what was not. Matching is lexical token overlap, so "no match" means
no shared words, not that nothing relevant exists.
"""
from __future__ import annotations

import re

from .tree import SCHEMA

MATCH_METHOD = "LEXICAL_TOKEN_OVERLAP"
MAX_QUERY_CHARS = 500
MAX_LIMIT = 50
MAX_LISTED = 50
_TOKEN = re.compile(r"[A-Za-z0-9]{3,}")


def _tokens(text):
    return {t.lower() for t in _TOKEN.findall(text)}


def _ensure(tree):
    tree.db.executescript("""
    CREATE TABLE IF NOT EXISTS conversation_span_index(
        branch TEXT NOT NULL, turn_id TEXT NOT NULL, start INTEGER NOT NULL, stop INTEGER NOT NULL,
        actor TEXT NOT NULL, disposition TEXT NOT NULL, rule TEXT, obligation_id TEXT,
        tokens TEXT NOT NULL, PRIMARY KEY(branch, turn_id, start));
    CREATE TABLE IF NOT EXISTS conversation_index_meta(
        branch TEXT PRIMARY KEY, event_head TEXT, turn_head TEXT);
    """)


def _heads(tree):
    return tree.replay()["head"], tree.custody_report()["head"]


def build_index(tree, branch):
    """Rebuild the derived span index for one branch from custody and the event chain."""
    _ensure(tree)
    ledger = tree.ledger(branch)
    event_head, turn_head = _heads(tree)
    texts = {t["turn_id"]: t["content"] for t in tree.turns()}
    rows = []
    for span in ledger["spans"]:
        text = ""
        if span["rule"] != "NOT_UTF8_TEXT":
            text = texts[span["turn_id"]].decode("utf-8")[span["start"]:span["end"]]
        rows.append((branch, span["turn_id"], span["start"], span["end"], span["actor"],
                     span["disposition"], span["rule"], span["obligation_id"],
                     " ".join(sorted(_tokens(text)))))
    tree.db.execute("BEGIN IMMEDIATE")
    try:
        tree.db.execute("DELETE FROM conversation_span_index WHERE branch=?", (branch,))
        tree.db.executemany("INSERT INTO conversation_span_index VALUES(?,?,?,?,?,?,?,?,?)", rows)
        tree.db.execute("INSERT OR REPLACE INTO conversation_index_meta VALUES(?,?,?)",
                        (branch, event_head, turn_head))
        tree.db.commit()
    except Exception:
        tree.db.rollback()
        raise
    return {"branch": branch, "spans": len(rows), "event_head": event_head, "turn_head": turn_head}


def index_status(tree, branch):
    _ensure(tree)
    row = tree.db.execute(
        "SELECT event_head,turn_head FROM conversation_index_meta WHERE branch=?", (branch,)).fetchone()
    if row is None:
        return "ABSENT"
    return "CURRENT" if tuple(row) == _heads(tree) else "STALE"


def _receipt(tree, branch, status, **fields):
    state = tree.replay()
    node = state["branches"].get(branch)
    return {"schema": SCHEMA, "status": status, "match_method": MATCH_METHOD,
            "scope": {"branch": branch, "snapshot": state["head"],
                      "packspec_version": node["packspecs"][-1]["version"] if node else None},
            "full_coverage_claimed": False, **fields}


def search(tree, branch, query, *, limit=10, include_superseded=False):
    """Search the spans in scope of a branch. Always returns a coverage receipt."""
    if branch not in tree.replay()["branches"]:
        raise ValueError("Unknown branch")
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError("Invalid limit")
    wanted = _tokens(query) if isinstance(query, str) and len(query) <= MAX_QUERY_CHARS else set()
    if not wanted:
        return {"results": [], "receipt": _receipt(tree, branch, "NOT_SEARCHED",
                                                   reason="Empty, oversize or token-free query")}
    status = index_status(tree, branch)
    if status != "CURRENT":
        # Never answer from an index that lags the source, and never call that "nothing found".
        return {"results": [], "receipt": _receipt(tree, branch, "INDEX_INCOMPLETE", index=status)}
    in_scope = excluded = unknown = superseded = 0
    matches, unmatched_residual = [], 0
    for turn_id, start, stop, actor, disposition, rule, obligation_id, tokens in tree.db.execute(
            "SELECT turn_id,start,stop,actor,disposition,rule,obligation_id,tokens"
            " FROM conversation_span_index WHERE branch=? ORDER BY rowid", (branch,)):
        if disposition == "UNKNOWN":
            unknown += 1
            continue
        is_superseded = rule == "SUPERSEDED"
        if disposition == "EXCLUDED_BY_RULE" and not (is_superseded and include_superseded):
            excluded += 1
            superseded += is_superseded
            continue
        in_scope += 1
        score = len(wanted & set(tokens.split()))
        if score:
            matches.append((score, turn_id, start, stop, actor, disposition, rule, obligation_id))
        elif disposition == "RESIDUAL":
            unmatched_residual += 1
    matches.sort(key=lambda m: -m[0])  # stable: ties keep conversation order
    results = []
    for score, turn_id, start, stop, actor, disposition, rule, obligation_id in matches[:limit]:
        fetched = tree.read(turn_id, start, stop)
        results.append({"turn_id": turn_id, "start": start, "end": stop, "score": score,
                        "disposition": disposition, "current": rule != "SUPERSEDED",
                        "obligation_id": obligation_id, "actor": actor,
                        "authority": fetched["authority"], "handling": fetched["handling"],
                        "content": fetched["content"].decode("utf-8")})
    left = matches[limit:]
    if not matches:
        state = "NONE_IN_SCOPE"
    elif left:
        state = "PARTIAL"
    else:
        state = "ALL_MATCHES_RETURNED"
    receipt = _receipt(
        tree, branch, state, spans_in_scope=in_scope, matched=len(matches), returned=len(results),
        not_returned={"count": len(left),
                      "ids": ["%s:%d-%d" % (m[1], m[2], m[3]) for m in left[:MAX_LISTED]]},
        unmatched_residual=unmatched_residual, excluded_by_rule=excluded,
        superseded_withheld=superseded, unknown=unknown)
    return {"results": results, "receipt": receipt}


def get(tree, branch, turn_id, start=None, end=None):
    """Fetch a turn or span by ID and say whether it is in scope of the branch."""
    fetched = tree.read(turn_id, start, end)
    return {**fetched, "branch": branch, "in_scope": turn_id in tree.visible_turns(branch)}
