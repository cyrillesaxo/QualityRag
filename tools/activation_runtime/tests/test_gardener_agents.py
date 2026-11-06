"""Developers and agents reach the Gardener through the SDK, the CLI and the MCP server."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.activation_runtime.authority import issue_access
from tools.activation_runtime.service import Application, server

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk" / "python"))
from qualityrag_activation import Client  # noqa: E402

AT = "2026-11-05T12:00:00Z"


class GardenerAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.key = Ed25519PrivateKey.generate()
        self.app = Application(self.temp.name, access_keys={"issuer": self.key.public_key()}, release_keys={}, clock=lambda: AT)
        self.http = server(self.app)
        Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.endpoint = f"http://127.0.0.1:{self.http.server_port}"
        self.agent = self.token("agent-7", ["read", "write"])
        self.reader = self.token("viewer", ["read"])

    def token(self, subject, scopes):
        return issue_access(subject=subject, tenant="lab", scopes=scopes, key=self.key, key_id="issuer",
                            issued_at="2026-11-04T00:00:00Z", expires_at="2026-11-06T00:00:00Z")

    def token_file(self, token):
        path = Path(self.temp.name) / ("token-" + str(abs(hash(json.dumps(token, sort_keys=True)))) + ".json")
        path.write_text(json.dumps(token))
        return path

    def mcp(self, token, messages):
        env = {**os.environ, "QUALITYRAG_ENDPOINT": self.endpoint, "QUALITYRAG_TOKEN_FILE": str(self.token_file(token))}
        run = subprocess.run([sys.executable, "-m", "tools.activation_runtime.mcp_server"], cwd=ROOT, env=env,
                             input="\n".join(json.dumps(m) for m in messages) + "\n", capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        return [json.loads(line) for line in run.stdout.splitlines() if line.strip()]

    def call(self, i, name, arguments):
        return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": arguments}}

    def test_sdk_query_and_scopes(self):
        client = Client(self.endpoint, self.agent)
        source = client.upload(b"research notes")["source_sha256"]
        client.garden_event(event_id="e1", operation="PROPOSE", branch="gate", source_sha256=source,
                            source_ref="notes#1", statement="An evidence gate stops unsupported answers")
        client.garden_event(event_id="e2", operation="CHALLENGE", branch="gate", source_sha256=source,
                            source_ref="notes#2", statement="Lexical labels let adversarial questions through")
        result = client.garden_query(open_challenge=True)
        self.assertEqual([b["branch"] for b in result["branches"]], ["gate"])
        self.assertEqual(Client(self.endpoint, self.reader).garden_query(since=1)["events"][0]["event_id"], "e2")
        with self.assertRaises(HTTPError) as denied:  # read-only token cannot grow the tree
            Client(self.endpoint, self.reader).garden_event(event_id="e3", operation="PROPOSE", branch="x", source_sha256=source,
                                                            source_ref="n", statement="s")
        self.assertEqual(denied.exception.code, 403)
        with self.assertRaises(HTTPError) as review:  # write scope still cannot prune
            client.garden_event(event_id="e4", operation="PRUNE", branch="gate", source_sha256=source, source_ref="n", statement="s")
        self.assertEqual(review.exception.code, 403)
        with self.assertRaises(HTTPError):
            client.garden_query(unknown=True)

    def test_mcp_agent_grows_and_queries_the_tree(self):
        out = self.mcp(self.agent, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            self.call(3, "garden_propose", {"branch": "gate", "statement": "An evidence gate stops unsupported answers",
                                            "source_text": "Meeting notes, 5 Nov", "source_ref": "notes#1"}),
            self.call(4, "garden_propose", {"branch": "llm-labeler", "statement": "Label with an LLM and exact quotes", "parents": ["gate"]}),
            self.call(5, "garden_challenge", {"branch": "llm-labeler", "statement": "Self-abstaining LLMs may match it"}),
            self.call(6, "garden_query", {"open_challenge": True}),
            self.call(7, "garden_query", {"since": 2}),
            self.call(8, "garden_test", {"branch": "llm-labeler", "statement": "ran it", "evidence_ids": ["not-recorded"]}),
            self.call(9, "garden_prune", {"branch": "gate"}),
            self.call(10, "garden_query", {"bogus": 1}),
            {"jsonrpc": "2.0", "id": 11, "method": "ping"},
        ])
        by_id = {m["id"]: m for m in out}
        self.assertEqual(len(out), 11)  # the notification gets no reply
        self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "qualityrag-gardener")
        names = [t["name"] for t in by_id[2]["result"]["tools"]]
        self.assertEqual(names, ["garden_query", "garden_suggestions", "policy_test", "policy_advise", "policy_replay",
                                 "functional_siblings", "evidence_admit", "release_output", "garden_propose",
                                 "garden_challenge", "garden_test"])
        for i in (3, 4, 5):
            self.assertFalse(by_id[i]["result"]["isError"], by_id[i])
        self.assertEqual(by_id[4]["result"]["structuredContent"]["independent_validation"], "NOT_ESTABLISHED")
        self.assertEqual([b["branch"] for b in by_id[6]["result"]["structuredContent"]["branches"]], ["llm-labeler"])
        self.assertEqual([e["operation"] for e in by_id[7]["result"]["structuredContent"]["events"]], ["CHALLENGE"])
        self.assertTrue(by_id[8]["result"]["isError"])  # evidence must already be in the ledger
        self.assertEqual(by_id[9]["error"]["code"], -32602)  # no prune tool for agents
        self.assertTrue(by_id[10]["result"]["isError"])
        self.assertEqual(by_id[11]["result"], {})
        state = Client(self.endpoint, self.reader).garden_state()
        self.assertEqual({state["events"][e]["actor"] for e in state["order"]}, {"agent-7"})  # actor comes from the token
        self.assertEqual(state["branches"]["llm-labeler"]["parents"], ["gate"])

    def test_mcp_read_only_agent_tests_advises_and_replays_policy(self):
        ex = Client(self.endpoint, self.reader).policy_example()
        test_args = {k: ex[k] for k in ("pack", "documents", "retrieved", "question", "as_of")}
        out = self.mcp(self.reader, [
            self.call(1, "policy_test", test_args),
            self.call(2, "policy_replay", {"base": ex["pack"], "branch": ex["branch_pack"], "cases": ex["cases"], "as_of": ex["as_of"]}),
            self.call(3, "policy_test", {**test_args, "labeler": "llm"}),
            self.call(5, "functional_siblings", {k: ex["siblings_example"][k] for k in ("function", "contracts", "candidates", "as_of")}),
        ])
        by_id = {m["id"]: m for m in out}
        test = by_id[1]["result"]["structuredContent"]
        self.assertEqual(test["verdict"], "ADMIT")
        self.assertEqual(test["summary"]["qualified_requirements"], 2)
        self.assertEqual(by_id[2]["result"]["structuredContent"]["flipped"], 1)
        self.assertTrue(by_id[3]["result"]["isError"])  # unknown argument
        self.assertEqual(by_id[5]["result"]["structuredContent"]["contracts"]["join-and-separate"]["rejected"], ["rivet"])
        advice = self.mcp(self.reader, [self.call(4, "policy_advise", {"pack": ex["pack"], "test": test})])[0]
        ids = [f["id"] for f in advice["result"]["structuredContent"]["findings"]]
        self.assertIn("evidence.qualified-support", ids)

    def test_mcp_read_only_agent_is_refused(self):
        out = self.mcp(self.reader, [self.call(1, "garden_propose", {"branch": "b", "statement": "s", "source_text": "x"})])
        self.assertTrue(out[0]["result"]["isError"])
        self.assertIn("access denied", out[0]["result"]["content"][0]["text"])

    def test_cli_query_and_watch(self):
        client = Client(self.endpoint, self.agent)
        source = client.upload(b"notes")["source_sha256"]
        for i, branch in enumerate(("gate", "roots"), 1):
            client.garden_event(event_id=f"e{i}", operation="PROPOSE", branch=branch, source_sha256=source,
                                source_ref="n", statement=f"hypothesis {branch}")
        token = str(self.token_file(self.reader))
        base = [sys.executable, "-m", "tools.activation_runtime.cli", "garden"]
        query = subprocess.run(base + ["query", "--endpoint", self.endpoint, "--token", token, "--text", "roots"],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual([b["branch"] for b in json.loads(query.stdout)["branches"]], ["roots"], query.stderr)
        watch = subprocess.run(base + ["watch", "--endpoint", self.endpoint, "--token", token, "--since", "1", "--max-polls", "1"],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual([json.loads(l)["event_id"] for l in watch.stdout.splitlines()], ["e2"], watch.stderr)


if __name__ == "__main__":
    unittest.main()
