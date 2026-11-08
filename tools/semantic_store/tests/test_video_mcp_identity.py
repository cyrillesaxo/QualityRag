"""OAuth resource-server staging: per-principal source isolation via MCP HTTP.

This test generates signed JWTs locally; it does not implement an IdP.
"""
import asyncio
import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_mcp_remote import create_remote_app
from video_catalog import write_evidence
from video_evidence import compile_video_evidence


class IdentityIsolationTests(unittest.TestCase):
    def test_two_signed_principals_cannot_read_each_others_sources(self):
        import httpx
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        async def check():
            with tempfile.TemporaryDirectory() as root:
                private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
                jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
                jwk.update({"kid":"test","alg":"RS256","use":"sig"})
                key_file=Path(root)/"keys.json"
                acl_file=Path(root)/"acl.json"
                key_file.write_text(json.dumps({"keys":[jwk]}))
                acl_file.write_text(json.dumps({"subjects":{
                    "alice":["video-a"],"bob":["video-b"]}}))
                for source_id in ("video-a","video-b"):
                    artifact=compile_video_evidence(
                        source_id=source_id,revision="r1",duration_ms=5000,
                        media_sha256=hashlib.sha256(source_id.encode()).hexdigest(),
                        witnesses=[{"id":"spoken","modality":"audio",
                            "interval":{"start_ms":100,"end_ms":600},
                            "provider":"test","text":"wheelchair technique narrated"}],
                        events=[])
                    write_evidence(root,artifact)

                env={
                    "QUALITYRAG_VIDEO_ROOT":root,
                    "QUALITYRAG_VIDEO_MCP_AUTH_MODE":"jwt",
                    "QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS":"video-a,video-b",
                    "QUALITYRAG_VIDEO_MCP_ALLOWED_HOSTS":"testserver",
                    "QUALITYRAG_VIDEO_MCP_ISSUER":"https://issuer.example",
                    "QUALITYRAG_VIDEO_MCP_AUDIENCE":"qualityrag-video",
                    "QUALITYRAG_VIDEO_MCP_JWKS_FILE":str(key_file),
                    "QUALITYRAG_VIDEO_MCP_ACL_FILE":str(acl_file),
                }
                app=create_remote_app(env)
                def token(subject):
                    now=int(time.time())
                    return jwt.encode({
                        "sub":subject,"iss":"https://issuer.example",
                        "aud":"qualityrag-video","iat":now,"exp":now+300,
                        "scope":"video:read"},private,algorithm="RS256",
                        headers={"kid":"test"})
                def hdr(subject):
                    return {"Authorization":"Bearer "+token(subject),
                            "Accept":"application/json, text/event-stream",
                            "Content-Type":"application/json","Host":"testserver"}
                async with app.app.router.lifespan_context(app.app):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://testserver",timeout=30.0) as client:
                        async def query(subject,tool,args,number):
                            r=await client.post("/mcp",headers=hdr(subject),json={
                                "jsonrpc":"2.0","id":number,"method":"tools/call",
                                "params":{"name":tool,"arguments":args}})
                            self.assertEqual(r.status_code,200,r.text)
                            return r.json()["result"]
                        for sub,allowed,denied in [
                            ("alice","video-a","video-b"),
                            ("bob","video-b","video-a")]:
                            found=await query(sub,"search_video_evidence",
                                               {"query":"wheelchair"},1)
                            serialized=json.dumps(found)
                            self.assertIn(allowed,serialized)
                            self.assertNotIn(denied,serialized)
                            inspected=await query(sub,"inspect_video_evidence",
                                                  {"source_id":denied},2)
                            self.assertTrue(inspected.get("isError",False))
                            researched=await query(sub,"research_video_question",
                                                   {"query":"wheelchair"},3)
                            serialized=json.dumps(researched)
                            self.assertIn(allowed,serialized)
                            self.assertNotIn(denied,serialized)
                        invalid=await client.post("/mcp",headers={
                            "Authorization":"Bearer invalid","Host":"testserver",
                            "Accept":"application/json, text/event-stream"},
                            json={"jsonrpc":"2.0","id":4,"method":"tools/list"})
                        self.assertEqual(invalid.status_code,401)
        asyncio.run(check())


if __name__=="__main__":
    unittest.main()
