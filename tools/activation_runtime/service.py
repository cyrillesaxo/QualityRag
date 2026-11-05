"""Authenticated local review/API service. Bind to loopback or put behind TLS.

Tenant is derived only from an authenticated signed principal. Source contents,
credentials and exception details are never logged or included in error replies.
"""
from __future__ import annotations

import base64
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from jsonschema.exceptions import ValidationError
from pathlib import Path
from threading import Event,Thread

from .authority import authenticate
from .artifacts import ArtifactStore
from .common import canonical, strict_json, identity
from .contracts import validate
from .pipeline import activate_signed
from .gardener import Gardener
from .proposals import suggest,record_outcome

WEB=Path(__file__).with_name("web")


class Application:
    def __init__(self,root,*,access_keys,release_keys,minimum_sequence=1,clock=None,preservation_authorities=None):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.access_keys=access_keys;self.release_keys=release_keys
        self.minimum_sequence=minimum_sequence
        self.clock=clock or (lambda:datetime.now(timezone.utc).isoformat())
        self.proposal_cache={}
        self.preservation_authorities=preservation_authorities or {}

    def principal(self,authorization,scope):
        if not isinstance(authorization,str) or not authorization.startswith("Bearer "):
            raise PermissionError("Authentication required")
        encoded=authorization[7:]
        if len(encoded)>32768:raise PermissionError("Token byte budget")
        try:
            token=strict_json(base64.urlsafe_b64decode(encoded+"="*((-len(encoded))%4)))
            return authenticate(token,self.access_keys,as_of=self.clock(),scope=scope)
        except (ValueError,KeyError,TypeError) as exc:raise PermissionError("Authentication refused") from exc

    def store(self,principal):
        return ArtifactStore(self.root/"objects",tenant=principal.tenant)

    def garden_path(self,principal):
        directory=self.root/"gardens"/principal.tenant
        directory.mkdir(parents=True,exist_ok=True)
        return directory/"events.sqlite"

    def dispatch(self,route,body,authorization):
        if not isinstance(body,dict):raise ValueError("JSON object required")
        scope="write" if route in {"source","gardener/event","reviewed-run"} else "read"
        if route=="gardener/event" and body.get("operation") in {"PRUNE","REOPEN","SYNTHESIZE"}:scope="review"
        if route=="gardener/outcome":scope="review"
        principal=self.principal(authorization,scope)
        store=self.store(principal)
        if route=="source":
            if set(body)!={"base64"}:raise ValueError("Unsupported source options")
            data=base64.b64decode(body["base64"],validate=True)
            return {"source_sha256":store.put(data),"bytes":len(data)}
        if route=="reviewed-run":
            if set(body)!={"base64","request"} or not isinstance(body["request"],dict):
                raise ValueError("Original source and signed request required")
            # Require both scopes before staging any bytes. Staging never grants approval.
            self.principal(authorization,"read")
            request=body["request"]
            if set(request)!={"source_sha256","artifact","signed_manifest","policy_ir","contract","signed_review","allow_fallback"}:
                raise ValueError("Unsupported reviewed activation options")
            data=base64.b64decode(body["base64"],validate=True)
            if not 0<len(data)<=65536 or __import__("hashlib").sha256(data).hexdigest()!=request["source_sha256"]:
                raise ValueError("Original source differs from signed request")
            validate("transform",request["artifact"])
            store.put(data);store.put(canonical(request["artifact"]))
            return self.dispatch("activate-plan",request,authorization)
        if route=="fallback":
            if set(body)!={"source_sha256"}:raise ValueError("Unsupported fallback options")
            data=store.get(body["source_sha256"])
            return {"source_sha256":body["source_sha256"],"base64":base64.b64encode(data).decode(),
                    "fallback":"AUTHORIZED_ORIGINAL_BYTES"}
        if route=="validate":
            if set(body)!={"schema","value"}:raise ValueError("Unsupported validation options")
            validate(body["schema"],body["value"])
            return {"valid":True,"semantic_admission":"INCONCLUSIVE"}
        if route=="evaluate":
            if set(body)!={"source_sha256","artifact","signed_manifest","policy_ir"}:
                raise ValueError("Unsupported evaluation options")
            raw=store.get(body["source_sha256"])
            return activate_signed(raw,body["artifact"],signed_manifest=body["signed_manifest"],
                trusted_keys=self.release_keys,store=store,tenant=principal.tenant,
                minimum_sequence=self.minimum_sequence,ir=body["policy_ir"],witnesses=[],as_of=self.clock())
        if route=="observations":
            if set(body) not in ({"source_sha256","observations"},{"source_sha256","observations","rename"}):
                raise ValueError("Unsupported observation options")
            from .semantic_ir import evaluate
            return evaluate(store.get(body["source_sha256"]),{key:value for key,value in body.items() if key!="source_sha256"})
        if route=="activate-plan":
            if set(body)!={"source_sha256","artifact","signed_manifest","policy_ir","contract","signed_review","allow_fallback"}:
                raise ValueError("Unsupported reviewed activation options")
            authorities=self.preservation_authorities.get(principal.tenant)
            if not isinstance(authorities,dict):raise PermissionError("Tenant preservation authority unavailable")
            if not isinstance(body["contract"],dict):raise ValueError("Preservation contract required")
            author_key=authorities.get("authors",{}).get(body["contract"].get("author"))
            if author_key is None:raise PermissionError("Host author identity unavailable")
            from .reviewed_activation import execute
            from .authority import SQLiteNonceStore
            directory=self.root/"review-nonces";directory.mkdir(parents=True,exist_ok=True)
            return execute(store.get(body["source_sha256"]),body["artifact"],store=store,tenant=principal.tenant,
                signed_manifest=body["signed_manifest"],release_keys=self.release_keys,minimum_sequence=self.minimum_sequence,
                policy_ir=body["policy_ir"],contract=body["contract"],signed_review=body["signed_review"],
                reviewer_keys=authorities.get("review",{}),reviewer_subjects=authorities.get("subjects",{}),
                author_public_key=author_key,nonce_store=SQLiteNonceStore(directory/(principal.tenant+".sqlite")),
                as_of=self.clock(),allow_fallback=body["allow_fallback"])
        if route=="gardener/event":
            required={"event_id","operation","branch","source_sha256","source_ref","statement","parents"}
            # evidence_ids is optional; TEST requires it and append() checks each ID exists in this tenant's ledger.
            if not required<=set(body)<=required|{"evidence_ids"}:
                raise ValueError("Unsupported event options")
            store.get(body["source_sha256"])
            garden=Gardener(self.garden_path(principal))
            try:return garden.append(**body,actor=principal.subject,at=self.clock())
            finally:garden.close()
        if route=="gardener/outcome":
            if set(body)!={"proposal_id","verdict","useful","elapsed_ms","false_merge"}:
                raise ValueError("Unsupported review outcome options")
            return record_outcome(self.garden_path(principal),actor=principal.subject,**body)
        if route=="gardener/query":
            from .gardener import QUERY_KEYS,query
            if not set(body)<=QUERY_KEYS:raise ValueError("Unsupported query options")
            garden=Gardener(self.garden_path(principal))
            try:return query(garden.replay(),**body)
            finally:garden.close()
        if route=="gardener/state":
            if body:raise ValueError("Unsupported state options")
            garden=Gardener(self.garden_path(principal))
            try:return garden.replay()
            finally:garden.close()
        if route=="gardener/proposals":
            if body:raise ValueError("Unsupported proposal options")
            return suggest(self.garden_path(principal))
        if route.startswith("policy/"):
            from . import governance
            as_of=body.get("as_of") or self.clock()
            if route=="policy/example":
                if body:raise ValueError("Unsupported example options")
                from . import siblings
                return {**governance.example(),"siblings_example":siblings.example()}
            if route=="policy/siblings":
                from . import siblings
                if not {"function","contracts","candidates"}<=set(body)<={"function","contracts","candidates","as_of"}:
                    raise ValueError("Unsupported sibling options")
                return siblings.feasibility(body["function"],body["contracts"],body["candidates"],as_of=as_of)
            if route=="policy/test":
                if not {"pack","documents","retrieved"}<=set(body)<={"pack","documents","retrieved","question","as_of"}:
                    raise ValueError("Unsupported policy test options")
                return governance.policy_test(body["pack"],body["documents"],body["retrieved"],as_of=as_of,question=body.get("question"))
            if route=="policy/advise":
                if not set(body)<={"pack","test","benchmark","far_limit"}:raise ValueError("Unsupported advisor options")
                garden=Gardener(self.garden_path(principal))
                try:state=garden.replay()
                finally:garden.close()
                limit=body.get("far_limit",0.10)
                if not isinstance(limit,(int,float)) or isinstance(limit,bool) or not 0<=limit<=1:raise ValueError("far_limit")
                return governance.advise(pack=body.get("pack"),test=body.get("test"),garden=state,
                                         benchmark=body.get("benchmark"),far_limit=limit)
            if route=="policy/replay":
                if not {"base","branch","cases"}<=set(body)<={"base","branch","cases","as_of"}:
                    raise ValueError("Unsupported replay options")
                return governance.replay(body["base"],body["branch"],body["cases"],as_of=as_of)
        if route=="status":
            if body:raise ValueError("Unsupported status options")
            return {"tenant":principal.tenant,"principal":principal.subject,"scopes":sorted(principal.scopes),
                    "mode":"RESEARCH","reviewed_activation_configured":bool(self.preservation_authorities.get(principal.tenant)),"can_generate":False}
        raise ValueError("Unknown API route")

    def start_proposal_loop(self,principals,*,interval_seconds=60):
        # Principals are a trusted, explicitly authorized host allowlist.
        if type(interval_seconds) is not int or not 1<=interval_seconds<=3600:
            raise ValueError("Bounded polling interval")
        from .authority import Principal
        if not isinstance(principals,list) or len(principals)>32 or any(not isinstance(p,Principal) or "read" not in p.scopes for p in principals):
            raise PermissionError("Authorized source allowlist required")
        stop=Event()
        def tick():
            while not stop.is_set():
                for principal in principals:
                    try:self.proposal_cache[principal.tenant]=suggest(self.garden_path(principal))
                    except (ValueError,OSError):self.proposal_cache[principal.tenant]={"status":"UNKNOWN"}
                stop.wait(interval_seconds)
        thread=Thread(target=tick,daemon=True)
        thread.start()
        return stop,thread


def handler(application):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,raw,content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(raw)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            assets={"/":"index.html","/app.js":"app.js","/garden.js":"garden.js","/governance.js":"governance.js","/style.css":"style.css"}
            if self.path not in assets:self.reply(404,b'{"error":"NOT_FOUND"}');return
            path=WEB/assets[self.path]
            mime={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".css":"text/css; charset=utf-8"}
            self.reply(200,path.read_bytes(),mime[path.suffix])
        def do_POST(self):
            try:
                size=int(self.headers.get("Content-Length","0"))
                if not 0<size<=524288:raise ValueError("Request limit")
                body=strict_json(self.rfile.read(size))
                if not self.path.startswith("/api/"):raise ValueError("API route")
                result=application.dispatch(self.path[5:],body,self.headers.get("Authorization"))
                self.reply(200,canonical(result))
            except PermissionError:self.reply(403,b'{"error":"ACCESS_DENIED"}')
            except (ValueError,KeyError,TypeError,FileNotFoundError,ValidationError):self.reply(400,b'{"error":"INVALID_OR_UNAVAILABLE_INPUT"}')
            except Exception:self.reply(500,b'{"error":"INTERNAL_FAILURE"}')
    return Handler


def server(application,*,host="127.0.0.1",port=0):
    if host not in {"127.0.0.1","::1","localhost"}:raise ValueError("Direct server must bind to loopback; use a TLS gateway for remote access")
    return ThreadingHTTPServer((host,port),handler(application))
