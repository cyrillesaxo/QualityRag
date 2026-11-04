import base64
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.authority import issue_access,review_binding,verify_review
from tools.activation_runtime.service import Application,server
from tools.activation_runtime.artifacts import make_manifest,sign_manifest
from tools.activation_runtime.common import canonical
from tools.activation_runtime.pipeline import encode
from test_runtime import policy,AT

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"sdk"/"python"))
from qualityrag_activation import Client


class ServiceSDKTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.access=Ed25519PrivateKey.generate();self.release=Ed25519PrivateKey.generate()
        self.token=self.make_token("alice","a")
        self.app=Application(self.temp.name,access_keys={"issuer":self.access.public_key()},
                             release_keys={"release":self.release.public_key()},clock=lambda:AT)
        self.http=server(self.app);self.thread=Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
        self.endpoint="http://127.0.0.1:"+str(self.http.server_port)
        self.client=Client(self.endpoint,self.token)

    def make_token(self,name,tenant,scopes=None):
        return issue_access(subject=name,tenant=tenant,scopes=scopes or ["read","write","review"],
                key=self.access,key_id="issuer",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")

    def request(self):
        raw=b'{"instruction":"NOT permitted","unit":"mg"}'
        source=self.client.upload(raw)["source_sha256"]
        artifact=encode(raw,{"instruction":"i","unit":"u"})
        artifact_sha=self.client.upload(canonical(artifact))["source_sha256"]
        ir=policy()
        manifest=make_manifest(tenant="a",policy_ir_sha256=ir["ir_sha256"],source_sha256=source,artifact_sha256=artifact_sha,sequence=1)
        signed=sign_manifest(manifest,self.release,key_id="release",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
        return {"source_sha256":source,"artifact":artifact,"signed_manifest":signed,"policy_ir":ir}

    def test_python_typescript_actual_http_finite_verdict_parity(self):
        request=self.request()
        py=self.client.evaluate(**request)
        sdk=Path(__file__).resolve().parents[3]/"sdk"/"typescript"/"src"/"activation.ts"
        script="import {ActivationClient} from "+json.dumps(sdk.as_uri())+";let text='';for await(const c of process.stdin)text+=c;const i=JSON.parse(text);const c=new ActivationClient(i.url,i.token);console.log(JSON.stringify(await c.evaluate(i.request)));"
        child=subprocess.run(["node","--input-type=module","-e",script],
            input=json.dumps({"url":self.endpoint,"token":self.token,"request":request}).encode(),capture_output=True,timeout=10)
        self.assertEqual(child.returncode,0,child.stderr.decode())
        ts=json.loads(child.stdout)
        self.assertEqual(py,ts)
        self.assertEqual(py["finite_constraint_result"],"SAT")
        self.assertFalse(py["can_generate"])
        self.assertEqual(base64.b64decode(self.client.fallback(request["source_sha256"])["base64"]),b'{"instruction":"NOT permitted","unit":"mg"}')

    def test_cross_tenant_guessed_id_denied_and_scope_enforced(self):
        request=self.request()
        foreign=Client(self.endpoint,self.make_token("bob","b"))
        with self.assertRaises(HTTPError):foreign.fallback(request["source_sha256"])
        reader=Client(self.endpoint,self.make_token("reader","a",["read"]))
        with self.assertRaises(HTTPError):reader.upload(b"secret")
        with self.assertRaises(HTTPError):self.client.evaluate(**{**request,"tenant":"b"})
        with self.assertRaises(HTTPError):self.client.evaluate(**{**request,"as_of":"2026-11-04T00:00:00Z"})

    def test_real_ui_assets_and_no_inline_script(self):
        from urllib.request import urlopen
        with urlopen(self.endpoint) as response:
            body=response.read()
            self.assertIn(b"Research review",body)
            self.assertIn("script-src 'self'",response.headers["Content-Security-Policy"])
        self.assertNotIn(b"onclick=",body)

    def test_signed_review_independence_replay_and_binding(self):
        from signed_gate import SQLiteNonceStore
        author=Ed25519PrivateKey.generate();reviewer=Ed25519PrivateKey.generate()
        context={"source":"a"*64,"policy":"b"*64,"grammar":"c"*64,"model":"d"*64,"decoder":"e"*64,"run":"run1"}
        envelope=review_binding(context,decision="APPROVE",reviewer="reviewer",author_key_id="author",key=reviewer,key_id="reviewer",
            issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce="once")
        store=SQLiteNonceStore(Path(self.temp.name)/"nonces.sqlite")
        result=verify_review(envelope,{"reviewer":reviewer.public_key()},context=context,author_public_key=author.public_key(),as_of=AT,nonce_store=store,tenant="a")
        self.assertEqual(result["review"],"HOST_AUTHORIZED_APPROVAL")
        with self.assertRaises(PermissionError):
            verify_review(envelope,{"reviewer":reviewer.public_key()},context=context,author_public_key=author.public_key(),as_of=AT,nonce_store=store,tenant="a")
        with self.assertRaises(PermissionError):
            verify_review(envelope,{"reviewer":reviewer.public_key()},context=context,author_public_key=reviewer.public_key(),as_of=AT,nonce_store=store,tenant="a")
