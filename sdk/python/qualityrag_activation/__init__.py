"""Typed wire client for the authenticated QualityRag activation API."""
import base64
import json
import math
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,HTTPRedirectHandler,build_opener
from typing import Literal,TypedDict,NotRequired


class ValidationResult(TypedDict):
    valid: Literal[True]
    semantic_admission: Literal["INCONCLUSIVE"]


class FiniteReceipt(TypedDict):
    schema: Literal["qualityrag.finite-activation-receipt/v0.1"]
    source_sha256: str
    artifact_sha256: str
    policy_ir_sha256: str
    finite_constraint_result: Literal["SAT","UNSAT","UNKNOWN"]
    qualityrag_admission: Literal["INCONCLUSIVE","REFUSE"]
    can_generate: Literal[False]
    trace: list[str]
    action: Literal["REFUSE","REQUIRES_REVIEW"]
    reason: str|None
    research_output: dict[str,str|int|float|bool|None]|None
    fallback: dict[str,object]
    gate: dict[str,object]
    limitations: str
    compatibility: NotRequired[dict[str,object]]


class ReviewedActivationResult(TypedDict):
    schema: Literal["qualityrag.reviewed-activation/v1"]
    tenant: str
    source_sha256: str
    artifact_sha256: str
    contract_sha256: str
    policy_ir_sha256: str
    action: Literal["REQUIRES_REVIEW","REFUSE","FALLBACK"]
    finite_constraint_result: Literal["SAT","UNSAT","UNKNOWN"]
    output: dict[str,str|int|float|bool|None]|None
    qualityrag_admission: Literal["INCONCLUSIVE"]
    can_generate: Literal[False]
    execution: dict[str,object]
    candidate_audit: dict[str,object]
    preservation_review: dict[str,object]
    compatibility: dict[str,object]
    canonical_candidate: FiniteReceipt
    fallback_authority: Literal["DISABLED","SAME_SIGNED_SOURCE_AND_REVIEWED_CONTRACT"]
    evidence_boundary: str


class ObservationGraphResult(TypedDict):
    schema: Literal["qualityrag.observation-result/v1"]
    ast: dict[str,object]
    transition: dict[str,object]|None
    source_sha256: str
    type_status: Literal["WELL_TYPED"]
    domain_validity: Literal["UNKNOWN"]
    canonical_apx_parity: Literal["NOT_ESTABLISHED"]
    can_generate: Literal[False]


class FallbackResult(TypedDict):
    source_sha256: str
    base64: str
    fallback: Literal["AUTHORIZED_ORIGINAL_BYTES"]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise HTTPError(req.full_url,code,"Activation redirect refused",headers,fp)


def _endpoint(base_url):
    if not isinstance(base_url,str) or "\\" in base_url or any(ord(c)<=32 or ord(c)==127 for c in base_url):
        raise ValueError("Trusted HTTPS or loopback endpoint required")
    try:
        parsed=urlsplit(base_url)
        port=parsed.port
        valid=(parsed.scheme in {"http","https"} and parsed.hostname
               and parsed.username is None and parsed.password is None
               and not parsed.query and not parsed.fragment
               and (port is None or 1<=port<=65535)
               and (parsed.scheme=="https" or parsed.hostname=="127.0.0.1"))
    except ValueError as exc:raise ValueError("Invalid activation endpoint") from exc
    if not valid:raise ValueError("Trusted HTTPS or loopback endpoint required")
    return base_url.rstrip("/")


class Client:
    def __init__(self,base_url,token,*,timeout=10):
        self.url=_endpoint(base_url)
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=60:
            raise ValueError("Bounded positive timeout required")
        self.token=base64.urlsafe_b64encode(json.dumps(token,separators=(",",":"),allow_nan=False).encode()).decode().rstrip("=")
        self.timeout=timeout
        self.opener=build_opener(_NoRedirect())

    def request(self,route,payload):
        if route not in {"validate","evaluate","activate-plan","reviewed-run","observations","fallback","source","status","gardener/state","gardener/evolution","gardener/proposals","gardener/event","gardener/outcome","gardener/query","policy/example","policy/test","policy/advise","policy/replay","policy/siblings"}:
            raise ValueError("Unsupported SDK route")
        request=Request(self.url+"/api/"+route,data=json.dumps(payload,allow_nan=False).encode(),
                        headers={"Content-Type":"application/json","Authorization":"Bearer "+self.token},method="POST")
        with self.opener.open(request,timeout=self.timeout) as response:
            return json.load(response)

    def validate(self,schema:str,value:object)->ValidationResult:return self.request("validate",{"schema":schema,"value":value})
    def evaluate(self,**payload)->FiniteReceipt:return self.request("evaluate",payload)
    def activate_plan(self,**payload)->ReviewedActivationResult:return self.request("activate-plan",payload)
    def run_reviewed(self,raw:bytes,request:dict[str,object])->ReviewedActivationResult:return self.request("reviewed-run",{"base64":base64.b64encode(raw).decode(),"request":request})
    def observations(self,**payload)->ObservationGraphResult:return self.request("observations",payload)
    def trace(self,**payload)->list[str]:return self.evaluate(**payload)["trace"]
    def fallback(self,source_sha256:str)->FallbackResult:return self.request("fallback",{"source_sha256":source_sha256})
    def upload(self,raw):return self.request("source",{"base64":base64.b64encode(raw).decode()})

    # ---- Semantic Gardener -------------------------------------------------------------
    # Actor and time are set by the server from the signed token; agents with write scope can
    # propose, challenge and test, while prune, reopen and synthesize need review scope.
    def garden_state(self)->dict[str,object]:return self.request("gardener/state",{})
    def garden_evolution(self)->dict[str,object]:return self.request("gardener/evolution",{})
    def garden_query(self,**filters)->dict[str,object]:
        """Filters: text, evidence_status, open_challenge, active, lineage_of, depends_on, since, limit."""
        return self.request("gardener/query",filters)
    def garden_suggestions(self)->dict[str,object]:return self.request("gardener/proposals",{})
    def garden_event(self,*,event_id:str,operation:str,branch:str,source_sha256:str,source_ref:str,
                     statement:str,parents:list[str]|None=None,evidence_ids:list[str]|None=None)->dict[str,object]:
        body={"event_id":event_id,"operation":operation,"branch":branch,"source_sha256":source_sha256,
              "source_ref":source_ref,"statement":statement,"parents":list(parents or [])}
        if evidence_ids is not None:body["evidence_ids"]=list(evidence_ids)
        return self.request("gardener/event",body)
    def policy_example(self)->dict[str,object]:return self.request("policy/example",{})
    def policy_test(self,*,pack:dict,documents:list,retrieved:list[str],question:str|None=None,as_of:str|None=None)->dict[str,object]:
        """Run the gate on retrieved chunks and explain which spans it counted. Read scope; writes nothing."""
        body={"pack":pack,"documents":documents,"retrieved":list(retrieved)}
        if question:body["question"]=question
        if as_of:body["as_of"]=as_of
        return self.request("policy/test",body)
    def policy_advise(self,*,pack:dict|None=None,test:dict|None=None,benchmark:dict|None=None,far_limit:float|None=None)->dict[str,object]:
        """Governance findings: trust store, single-origin requirements, qualified spans, calibration, open challenges."""
        body={k:v for k,v in {"pack":pack,"test":test,"benchmark":benchmark,"far_limit":far_limit}.items() if v is not None}
        return self.request("policy/advise",body)
    def policy_replay(self,*,base:dict,branch:dict,cases:list,as_of:str|None=None)->dict[str,object]:
        """Re-evaluate recorded cases under two packs; every changed verdict and its effect."""
        body={"base":base,"branch":branch,"cases":cases}
        if as_of:body["as_of"]=as_of
        return self.request("policy/replay",body)
    def policy_siblings(self,*,function:str,contracts:dict,candidates:list,as_of:str|None=None)->dict[str,object]:
        """Feasible(s,F,C) per contract as SAT/UNSAT/UNKNOWN, functional siblings, regime boundaries, probes."""
        body={"function":function,"contracts":contracts,"candidates":candidates}
        if as_of:body["as_of"]=as_of
        return self.request("policy/siblings",body)
    def garden_outcome(self,*,proposal_id:str,verdict:str,useful:bool,elapsed_ms:int,false_merge:bool)->dict[str,object]:
        return self.request("gardener/outcome",{"proposal_id":proposal_id,"verdict":verdict,"useful":useful,
                                                "elapsed_ms":elapsed_ms,"false_merge":false_merge})

