"""Deployment configuration checks, not a claim of live production readiness."""
import unittest
from pathlib import Path

DEPLOY=Path(__file__).resolve().parent

class DeploymentChecks(unittest.TestCase):
    def test_loopback_and_dedicated_identity(self):
        service=(DEPLOY/"qualityrag-governance.service").read_text()
        self.assertIn("User=qualityrag-governance", service)
        self.assertIn("Group=qualityrag-governance", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("IPAddressDeny=any", service)
        self.assertIn("IPAddressAllow=localhost", service)
        self.assertIn("ReadWritePaths=/var/lib/qualityrag-governance",service)
        self.assertIn("--keys /etc/qualityrag-governance/authority.json",service)
        self.assertIn("--port 8769",service)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1",service)
        self.assertNotIn("local-issuer.key",service)
        self.assertNotIn("access-token.json",service)

    def test_https_ingress_is_api_only(self):
        caddy=(DEPLOY/"Caddyfile.example").read_text()
        self.assertIn("governance.example.com {",caddy)
        self.assertIn("@api path /api/*",caddy)
        self.assertIn("reverse_proxy 127.0.0.1:8769",caddy)
        self.assertIn('respond "Not Found" 404',caddy)
        self.assertNotIn("reverse_proxy 0.0.0.0:",caddy)
        self.assertNotIn("tls internal",caddy)

    def test_minimum_dependencies_are_pinned(self):
        req=(DEPLOY/"requirements-governance.txt").read_text()
        self.assertIn("cryptography==50.0.2",req)
        self.assertIn("jsonschema==4.25.1",req)
        self.assertNotIn("playwright",req)

    def test_runbook_requires_rotating_signed_read_scope(self):
        guide=(DEPLOY/"README.md").read_text()
        for phrase in ("read-scope-only", "short-lived", "renew it before expiry",
                       "No deploy without authenticated HTTPS backend",
                       "not per-ChatGPT-user identity", "minimum_sequence",
                       "SQLite backups", "qualityrag-mcp.netlify.app/mcp"):
            self.assertIn(phrase,guide)

if __name__=="__main__":
    unittest.main()
