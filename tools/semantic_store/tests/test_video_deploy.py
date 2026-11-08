"""Deployment-package regression checks; do not contact external hosts."""
import sys
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/"deploy"))
from smoke_https import smoke,NoRedirect


class DeploymentTests(unittest.TestCase):
    def test_smoke_rejects_non_https_and_invalid_token_before_network(self):
        for url in ("http://example.com/mcp","https://example.com/private",
                    "https://example.com/mcp?key=secret"):
            with self.subTest(url=url),self.assertRaises(ValueError):
                smoke(url,"test-token")
        with self.assertRaises(ValueError):
            smoke("https://example.com/mcp","secret\r\nInjected: true")

    def test_no_redirect_handler_prevents_secret_replay(self):
        with self.assertRaisesRegex(RuntimeError,"rejects redirects"):
            NoRedirect().redirect_request(None,None,302,"moved",{},
                                          "https://untrusted.example")

    def test_private_host_service_and_reverse_proxy_contract(self):
        service=(HERE/"deploy"/"qualityrag-video-mcp.service").read_text()
        config=(HERE/"deploy"/"Caddyfile.example").read_text()
        env=(HERE/"deploy"/"video-mcp.env.example").read_text()
        self.assertIn("User=qualityrag-video",service)
        self.assertIn("ProtectSystem=strict",service)
        self.assertIn("NoNewPrivileges=true",service)
        self.assertIn("IPAddressDeny=any",service)
        self.assertIn("IPAddressAllow=localhost",service)
        self.assertIn("reverse_proxy 127.0.0.1:8039",config)
        self.assertIn("QUALITYRAG_VIDEO_MCP_HOST=127.0.0.1",env)
        self.assertIn("QUALITYRAG_VIDEO_MCP_AUTH_MODE=jwt",env)
        self.assertIn("QUALITYRAG_VIDEO_MCP_RESOURCE_URL=https://",env)
        self.assertNotIn("QUALITYRAG_VIDEO_MCP_TOKEN=",env)


if __name__=="__main__":
    unittest.main()
