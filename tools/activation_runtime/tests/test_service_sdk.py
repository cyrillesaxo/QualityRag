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

    def request(self,*,alter_instruction=False):
        raw=b'{"instruction":"NOT permitted","unit":"mg"}'
        source=self.client.upload(raw)["source_sha256"]
        artifact=encode(raw,{"instruction":"i","unit":"u"})
        if alter_instruction:artifact["payload"]["i"]="permitted"
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

    def test_gardener_test_event_accepts_evidence_ids(self):
        import sqlite3
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research_ledger"))
        import ledger
        auth="Bearer "+base64.urlsafe_b64encode(canonical(self.token)).decode().rstrip("=")
        source=self.app.dispatch("source",{"base64":base64.b64encode(b"turn").decode()},auth)["source_sha256"]
        event=lambda i,op,**kw:{"event_id":i,"operation":op,"branch":"b","source_sha256":source,
                                "source_ref":"turn:1","statement":"Hypothesis "+i,"parents":[],**kw}
        self.app.dispatch("gardener/event",event("e1","PROPOSE"),auth)
        with self.assertRaises(ValueError):  # TEST still needs evidence
            self.app.dispatch("gardener/event",event("e2","TEST"),auth)
        with self.assertRaises(ValueError):  # unknown evidence is refused
            self.app.dispatch("gardener/event",event("e2","TEST",evidence_ids=["missing"]),auth)
        with self.assertRaises(ValueError):  # other extra options are still refused
            self.app.dispatch("gardener/event",event("e2","TEST",evidence_ids=["run1"],extra=1),auth)
        with sqlite3.connect(Path(self.temp.name)/"gardens"/"a"/"events.sqlite") as db:  # host-recorded evidence
            ledger.evidence(db,evidence_id="run1",kind="TEST_RESULT",uri="https://example.test/run1",
                            description="Host-recorded test",at=AT)
        state=self.app.dispatch("gardener/event",event("e2","TEST",evidence_ids=["run1"]),auth)
        self.assertEqual(state["events"]["e2"]["evidence_ids"],["run1"])
        self.assertEqual(state["events"]["e2"]["actor"],"alice")

    def test_cross_tenant_guessed_id_denied_and_scope_enforced(self):
        request=self.request()
        foreign=Client(self.endpoint,self.make_token("bob","b"))
        with self.assertRaises(HTTPError):foreign.fallback(request["source_sha256"])
        reader=Client(self.endpoint,self.make_token("reader","a",["read"]))
        with self.assertRaises(HTTPError):reader.upload(b"secret")
        with self.assertRaises(HTTPError):self.client.evaluate(**{**request,"tenant":"b"})
        with self.assertRaises(HTTPError):self.client.evaluate(**{**request,"as_of":"2026-11-04T00:00:00Z"})

    def test_all_sdk_and_cli_verbs_match_for_success_and_wording_loss_refusal(self):
        import contextlib
        import io
        from tools.activation_runtime.cli import main
        sdk=Path(__file__).resolve().parents[3]/"sdk"/"typescript"/"src"/"activation.ts"
        script="import {ActivationClient} from "+json.dumps(sdk.as_uri())+";let raw='';for await(const chunk of process.stdin)raw+=chunk;const i=JSON.parse(raw);const c=new ActivationClient(i.url,i.token);console.log(JSON.stringify({validate:await c.validate('receipt',i.receipt),evaluate:await c.evaluate(i.request),trace:await c.trace(i.request),fallback:await c.fallback(i.request.source_sha256)}));"
        token=Path(self.temp.name)/"token.json";token.write_text(json.dumps(self.token))
        for altered in (False,True):
            with self.subTest(altered=altered):
                request=self.request(alter_instruction=altered)
                receipt=self.client.evaluate(**request)
                py={"validate":self.client.validate("receipt",receipt),"evaluate":receipt,
                    "trace":self.client.trace(**request),"fallback":self.client.fallback(request["source_sha256"])}
                child=subprocess.run(["node","--input-type=module","-e",script],
                    input=json.dumps({"url":self.endpoint,"token":self.token,"request":request,"receipt":receipt}).encode(),
                    capture_output=True,timeout=10)
                self.assertEqual(child.returncode,0,child.stderr.decode())
                self.assertEqual(json.loads(child.stdout),py)
                self.assertEqual(receipt["finite_constraint_result"],"UNSAT" if altered else "SAT")
                self.assertFalse(receipt["can_generate"])
                if altered:self.assertIsNone(receipt["research_output"])
                request_file=Path(self.temp.name)/"request.json";request_file.write_text(json.dumps(request))
                receipt_file=Path(self.temp.name)/"receipt.json";receipt_file.write_text(json.dumps(receipt))
                for method in ("validate","evaluate","trace","fallback"):
                    args=["validate","receipt",str(receipt_file)] if method=="validate" else [method,"--endpoint",self.endpoint,"--token",str(token)]
                    if method in {"evaluate","trace"}:args += ["--request",str(request_file)]
                    if method=="fallback":args += ["--source-sha256",request["source_sha256"]]
                    out=io.StringIO()
                    with contextlib.redirect_stdout(out):main(args)
                    self.assertEqual(json.loads(out.getvalue()),py[method])

    def test_clients_refuse_redirect_without_forwarding_authorization(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        hits=[]
        class Target(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):hits.append(self.headers.get("Authorization"));self.send_response(204);self.end_headers()
            do_POST=do_GET
        target=ThreadingHTTPServer(("127.0.0.1",0),Target)
        self.addCleanup(target.server_close);self.addCleanup(target.shutdown)
        Thread(target=target.serve_forever,daemon=True).start()
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.send_response(302);self.send_header("Location","http://127.0.0.1:"+str(target.server_port)+"/api/status");self.end_headers()
        redirect=ThreadingHTTPServer(("127.0.0.1",0),Redirect)
        self.addCleanup(redirect.server_close);self.addCleanup(redirect.shutdown)
        Thread(target=redirect.serve_forever,daemon=True).start()
        url="http://127.0.0.1:"+str(redirect.server_port)
        with self.assertRaises(HTTPError):Client(url,self.token).request("status",{})
        sdk=Path(__file__).resolve().parents[3]/"sdk"/"typescript"/"src"/"activation.ts"
        script="import {ActivationClient} from "+json.dumps(sdk.as_uri())+";let raw='';for await(const c of process.stdin)raw+=c;const i=JSON.parse(raw);try{await new ActivationClient(i.url,i.token).request('status',{});process.exitCode=1;}catch{console.log('REFUSED');}"
        child=subprocess.run(["node","--input-type=module","-e",script],input=json.dumps({"url":url,"token":self.token}).encode(),capture_output=True,timeout=10)
        self.assertEqual(child.returncode,0,child.stderr.decode())
        self.assertEqual(child.stdout.strip(),b"REFUSED")
        self.assertEqual(hits,[])

    def test_sdk_endpoint_and_timeout_refusal(self):
        for url in ("http://127.0.0.1:80@elsewhere.invalid","https://user:password@example.invalid", "https://example.invalid?q=1", "https://example.invalid#fragment", "http://elsewhere.invalid", "https:///missing-host", "http://127.0.0.1:0", "https://example.invalid/\npath"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):Client(url,self.token)
        for timeout in (None,False,0,-1,float('nan'),float('inf'),61):
            with self.assertRaises(ValueError):Client(self.endpoint,self.token,timeout=timeout)

    def test_unsupported_options_and_cross_tenant_fallback_refuse_in_both_sdks_and_cli(self):
        import contextlib
        import io
        from tools.activation_runtime.cli import main
        request=self.request()
        extra={**request,"tenant":"other"}
        with self.assertRaises(HTTPError):self.client.trace(**extra)
        sdk=Path(__file__).resolve().parents[3]/"sdk"/"typescript"/"src"/"activation.ts"
        script="import {ActivationClient} from "+json.dumps(sdk.as_uri())+";let raw='';for await(const c of process.stdin)raw+=c;const i=JSON.parse(raw);const c=new ActivationClient(i.url,i.token);const calls=[()=>c.evaluate(i.extra),()=>c.trace(i.extra),()=>c.request('validate',{schema:'receipt',value:{},extra:true}),()=>c.request('fallback',{source_sha256:i.source,extra:true}),()=>new ActivationClient(i.url,i.foreign).fallback(i.source)];const result=[];for(const call of calls){try{await call();result.push('ACCEPTED');}catch{result.push('REFUSED');}}console.log(JSON.stringify(result));"
        child=subprocess.run(["node","--input-type=module","-e",script],input=json.dumps({"url":self.endpoint,"token":self.token,
            "foreign":self.make_token("bob","other"),"source":request["source_sha256"],"extra":extra}).encode(),capture_output=True,timeout=10)
        self.assertEqual(child.returncode,0,child.stderr.decode())
        self.assertEqual(json.loads(child.stdout),["REFUSED"]*5)
        token=Path(self.temp.name)/"token.json";token.write_text(json.dumps(self.token))
        payload=Path(self.temp.name)/"extra.json";payload.write_text(json.dumps(extra))
        for method in ("evaluate","trace"):
            with self.assertRaises(HTTPError):main([method,"--endpoint",self.endpoint,"--token",str(token),"--request",str(payload)])
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):main(["fallback","--endpoint",self.endpoint,"--token",str(token),"--source-sha256",request["source_sha256"],"--unsupported"])

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
