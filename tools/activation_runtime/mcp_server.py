"""MCP server (stdio) exposing the Semantic Gardener to AI agents.

An agent can read the research tree, query it, follow its growth, and append source-anchored
PROPOSE / CHALLENGE / TEST events. It can also test a policy against retrieved chunks, ask the
governance advisor for findings, and replay a policy branch over recorded cases (read only). It calls the same authenticated HTTP API as the console, so
the signed token decides what it may do: give agents a read+write token. PRUNE, REOPEN and
SYNTHESIZE need review scope and are deliberately not exposed as tools; no agent can mark a
claim validated. Configure with environment variables:

    QUALITYRAG_ENDPOINT    e.g. http://127.0.0.1:8769
    QUALITYRAG_TOKEN_FILE  path to the agent's signed access-token JSON

    python -m tools.activation_runtime.mcp_server
"""
from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError

SDK = str(Path(__file__).resolve().parents[2] / "sdk" / "python")
if SDK not in sys.path:
    sys.path.insert(0, SDK)

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "qualityrag-gardener", "version": "0.2.0"}
INSTRUCTIONS = ("The Semantic Gardener is an append-only research tree. Branches are hypotheses; events are "
                "PROPOSE, CHALLENGE, TEST, SYNTHESIZE, PRUNE and REOPEN. Query before you add: avoid duplicates, "
                "anchor every event to a source, and record objections as CHALLENGE rather than editing anything. "
                "evidence_status comes from the research ledger; nothing you do here validates a claim.")

_SOURCE = {
    "source_text": {"type": "string", "maxLength": 200000, "description": "Original text this event is anchored to; stored and hashed. Omit to reuse the branch's source."},
    "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$", "description": "Hash of a source already stored in this workspace."},
    "source_ref": {"type": "string", "maxLength": 1000, "description": "Where in the source (e.g. 'paper.pdf#p4', 'turn:12')."},
}
TOOLS = [
    {"name": "garden_query",
     "description": "Search the research tree. Filters combine with AND. Use `since` with the last head_sequence you saw to get only new events (watch it grow).",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "text": {"type": "string", "maxLength": 200}, "evidence_status": {"type": "string"},
         "open_challenge": {"type": "boolean"}, "active": {"type": "boolean"}, "lineage_of": {"type": "string"},
         "since": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "garden_suggestions",
     "description": "The Gardener's current review suggestions (possible duplicates, unresolved challenges) with suggested cost. Suggestions are not decisions.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
     "annotations": {"readOnlyHint": True}},
    {"name": "policy_test",
     "description": "Run the QualityRag gate on retrieved chunks and explain every counted and uncounted span: distinct origins, collapsed copies, qualifiers the gate does not evaluate. Writes nothing. ADMIT is metadata gate satisfaction, not authorization to act.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["pack", "documents", "retrieved"], "properties": {
         "pack": {"type": "object", "description": "PackSpec: id, version, requirements"},
         "documents": {"type": "array", "description": "Documents with id, origin and chunks (id, text, requirement_id, status)"},
         "retrieved": {"type": "array", "items": {"type": "string"}, "description": "Retrieved chunk IDs, in order"},
         "question": {"type": "string", "maxLength": 2000}, "as_of": {"type": "string"}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "policy_advise",
     "description": "Governance findings the gate does not check: reviewer trust store, single-origin requirements, evidence without max age, qualified supporting spans (pass a policy_test result), calibration (pass a benchmark report) and open Gardener challenges. Suggestions, not decisions.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "pack": {"type": "object"}, "test": {"type": "object", "description": "A policy_test result for the same pack"},
         "benchmark": {"type": "object", "description": "false_admission_rate, answer_rate, n, optional labeler and dataset"},
         "far_limit": {"type": "number", "minimum": 0, "maximum": 1}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "policy_replay",
     "description": "Re-evaluate recorded cases under a base pack and a branch pack and report every verdict that changed. Cases with expect_admit labels give false admissions removed, correct answers lost and both rates. Does not re-run retrieval or promote anything.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["base", "branch", "cases"], "properties": {
         "base": {"type": "object"}, "branch": {"type": "object"},
         "cases": {"type": "array", "description": "{id, evidence: [witness rows], expect_admit?: bool, question?}"}, "as_of": {"type": "string"}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "garden_propose",
     "description": "Add a hypothesis as a new branch, optionally forked from parent branches. Query first to avoid duplicates.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["branch", "statement"], "properties": {
         "branch": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"},
         "statement": {"type": "string", "minLength": 1, "maxLength": 2000},
         "parents": {"type": "array", "items": {"type": "string"}, "maxItems": 16}, **_SOURCE}}},
    {"name": "garden_challenge",
     "description": "Record a counterexample or objection against a branch. It stays open until a TEST follows.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["branch", "statement"], "properties": {
         "branch": {"type": "string"}, "statement": {"type": "string", "minLength": 1, "maxLength": 2000}, **_SOURCE}}},
    {"name": "garden_test",
     "description": "Record a test of a branch citing evidence IDs already recorded in the research ledger.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["branch", "statement", "evidence_ids"], "properties": {
         "branch": {"type": "string"}, "statement": {"type": "string", "minLength": 1, "maxLength": 2000},
         "evidence_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 50}, **_SOURCE}}},
]


class Gardener:
    def __init__(self, client):
        self.client = client

    def _source(self, args, branch=None):
        if args.get("source_text") is not None:
            raw = args["source_text"].encode("utf-8")
            sha = self.client.request("source", {"base64": base64.b64encode(raw).decode()})["source_sha256"]
            return sha, args.get("source_ref") or "agent-text"
        if args.get("source_sha256"):
            return args["source_sha256"], args.get("source_ref") or "stored-source"
        if branch:
            rows = self.client.garden_query(lineage_of=branch, limit=500)["branches"]
            row = next((r for r in rows if r["branch"] == branch), None)
            if row:
                return row["source_sha256"], args.get("source_ref") or row["source_ref"]
        raise ValueError("A source is required: give source_text or source_sha256")

    def _event(self, operation, args, *, branch, parents=(), evidence_ids=None, reuse_branch=None):
        sha, ref = self._source(args, reuse_branch)
        state = self.client.garden_event(event_id="agent-" + uuid.uuid4().hex, operation=operation, branch=branch,
                                         source_sha256=sha, source_ref=ref, statement=args["statement"],
                                         parents=list(parents), evidence_ids=evidence_ids)
        info = state["branches"][branch]
        return {"appended": operation, "branch": branch, "head_sequence": state.get("head_sequence"),
                "active": info["active"], "evidence_status": info["evidence_status"],
                "independent_validation": "NOT_ESTABLISHED"}

    def call(self, name, args):
        if name == "garden_query":
            return self.client.garden_query(**args)
        if name == "garden_suggestions":
            return self.client.garden_suggestions()
        if name == "policy_test":
            return self.client.policy_test(**args)
        if name == "policy_advise":
            return self.client.policy_advise(**args)
        if name == "policy_replay":
            return self.client.policy_replay(**args)
        if name == "garden_propose":
            parents = args.get("parents", [])
            return self._event("PROPOSE", args, branch=args["branch"], parents=parents,
                               reuse_branch=parents[0] if parents else None)
        if name == "garden_challenge":
            return self._event("CHALLENGE", args, branch=args["branch"], reuse_branch=args["branch"])
        if name == "garden_test":
            return self._event("TEST", args, branch=args["branch"], evidence_ids=args["evidence_ids"],
                               reuse_branch=args["branch"])
        raise KeyError(name)


def _check(schema, args):
    if not isinstance(args, dict):
        raise ValueError("Arguments must be an object")
    allowed = schema["properties"]
    extra = set(args) - set(allowed)
    if extra and schema.get("additionalProperties") is False:
        raise ValueError("Unsupported arguments: " + ", ".join(sorted(extra)))
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        raise ValueError("Missing arguments: " + ", ".join(missing))


def handle(gardener, message):
    """Return the JSON-RPC response for one message, or None for a notification."""
    method, mid = message.get("method"), message.get("id")
    if mid is None:
        return None
    def ok(result): return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        return ok({"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        tool = next((t for t in TOOLS if t["name"] == params.get("name")), None)
        if tool is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "Unknown tool"}}
        args = params.get("arguments") or {}
        try:
            _check(tool["inputSchema"], args)
            result = gardener.call(tool["name"], args)
            return ok({"content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}],
                       "structuredContent": result, "isError": False})
        except HTTPError as exc:
            reason = "access denied: this token's scope does not allow it" if exc.code == 403 else "the workspace refused the request"
            return ok({"content": [{"type": "text", "text": reason}], "isError": True})
        except (ValueError, KeyError, TypeError, URLError) as exc:
            return ok({"content": [{"type": "text", "text": "invalid request: " + str(exc)}], "isError": True})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}}


def main():
    from qualityrag_activation import Client
    endpoint = os.environ.get("QUALITYRAG_ENDPOINT")
    token_file = os.environ.get("QUALITYRAG_TOKEN_FILE")
    if not endpoint or not token_file:
        sys.stderr.write("Set QUALITYRAG_ENDPOINT and QUALITYRAG_TOKEN_FILE\n")
        sys.exit(2)
    token = json.loads(Path(token_file).read_text())
    gardener = Gardener(Client(endpoint, token))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            response = handle(gardener, message) if isinstance(message, dict) else \
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
