"""MCP protocol smoke: real SDK ASGI initialization and read-only tool listing.

Requires official mcp v1 + httpx (installed in dedicated CI step).
No external network connections or model inference.
"""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_mcp_remote import create_remote_app


class ProtocolTests(unittest.TestCase):
    def test_authorized_tool_discovery(self):
        import httpx
        async def run():
            with tempfile.TemporaryDirectory() as root:
                secret="s"*48
                app=create_remote_app({
                    "QUALITYRAG_VIDEO_ROOT":root,
                    "QUALITYRAG_VIDEO_MCP_TOKEN":secret,
                    "QUALITYRAG_VIDEO_MCP_ALLOWED_HOSTS":"testserver",
                })
                headers={"Authorization":"Bearer "+secret,
                         "Accept":"application/json, text/event-stream",
                         "Content-Type":"application/json",
                         "Host":"testserver"}
                async with app.app.router.lifespan_context(app.app):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://testserver",timeout=20.0) as client:
                        denied=await client.post("/mcp",json={"jsonrpc":"2.0","id":1,
                            "method":"initialize","params":{"protocolVersion":"2025-03-26",
                            "capabilities":{},"clientInfo":{"name":"test","version":"0"}}})
                        self.assertEqual(denied.status_code,401)
                        initialized=await client.post("/mcp",headers=headers,json={
                            "jsonrpc":"2.0","id":1,"method":"initialize",
                            "params":{"protocolVersion":"2025-03-26","capabilities":{},
                                      "clientInfo":{"name":"test","version":"0"}}})
                        self.assertEqual(initialized.status_code,200,initialized.text)
                        self.assertIn("result",initialized.json())
                        response=await client.post("/mcp",headers=headers,json={
                            "jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
                        self.assertEqual(response.status_code,200,response.text)
                        names={t["name"] for t in response.json()["result"]["tools"]}
                        self.assertEqual(names,{
                            "search_video_evidence","research_video_question",
                            "inspect_video_evidence"})
        asyncio.run(run())


if __name__=="__main__":
    unittest.main()
