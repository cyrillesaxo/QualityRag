"""No-model staging auth tests; verify denies happen before MCP execution."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_mcp_remote import BearerGate, RemoteConfigurationError, _config

TOKEN="A"*40


async def request(app, headers, scope_type="http"):
    sent=[]
    async def recv():
        return {"type":"http.request","body":b"","more_body":False}
    async def send(message):
        sent.append(message)
    await app({"type":scope_type,"method":"POST","path":"/mcp","headers":headers},recv,send)
    return sent


class RemoteSecurityTests(unittest.TestCase):
    def test_rejects_missing_short_token_and_nonloopback_binding(self):
        with tempfile.TemporaryDirectory() as root:
            base={"QUALITYRAG_VIDEO_ROOT":root,"QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS":"lesson-1"}
            with self.assertRaises(RemoteConfigurationError):
                _config(base)
            with self.assertRaises(RemoteConfigurationError):
                _config({**base,"QUALITYRAG_VIDEO_MCP_TOKEN":"short"})
            with self.assertRaises(RemoteConfigurationError):
                _config({**base,"QUALITYRAG_VIDEO_MCP_TOKEN":TOKEN,
                         "QUALITYRAG_VIDEO_MCP_HOST":"0.0.0.0"})
            self.assertEqual(_config({**base,"QUALITYRAG_VIDEO_MCP_TOKEN":TOKEN})["host"],"127.0.0.1")

    def test_explicit_source_scope_required_and_validated(self):
        with tempfile.TemporaryDirectory() as root:
            base={"QUALITYRAG_VIDEO_ROOT":root,"QUALITYRAG_VIDEO_MCP_TOKEN":TOKEN}
            with self.assertRaisesRegex(RemoteConfigurationError,"source allowlist"):
                _config(base)
            with self.assertRaises(RemoteConfigurationError):
                _config({**base,"QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS":"../other"})
            scoped=_config({**base,"QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS":"lesson-1,lesson-2"})
            self.assertEqual(scoped["source_ids"],frozenset({"lesson-1","lesson-2"}))

    def test_bearer_gate_checks_token_and_origin_before_dispatch(self):
        async def behind(scope,receive,send):
            await send({"type":"http.response.start","status":200,"headers":[]})
            await send({"type":"http.response.body","body":b"ok"})
        gate=BearerGate(behind,secret=TOKEN,origins=["https://approved.example"])
        async def run():
            for bad in [[],[(b"authorization",b"Bearer wrong")],
                        [(b"authorization",b"Basic "+TOKEN.encode())]]:
                denied=await request(gate,bad)
                self.assertEqual(denied[0]["status"],401)
                self.assertEqual(denied[1]["body"],b'{"error":"unauthorized"}')
            denied=await request(gate,[
                (b"authorization",b"Bearer "+TOKEN.encode()),
                (b"origin",b"https://evil.example")])
            self.assertEqual(denied[0]["status"],401)
            allowed=await request(gate,[
                (b"authorization",b"Bearer "+TOKEN.encode()),
                (b"origin",b"https://approved.example")])
            self.assertEqual(allowed[0]["status"],200)
        asyncio.run(run())

    def test_origin_validation_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            env={"QUALITYRAG_VIDEO_ROOT":root,"QUALITYRAG_VIDEO_MCP_TOKEN":TOKEN,
                 "QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS":"lesson-1"}
            for origin in ["*", "http://example.com","https://example.com/path"]:
                with self.assertRaises(RemoteConfigurationError):
                    _config({**env,"QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGINS":origin})


if __name__=="__main__":
    unittest.main()
