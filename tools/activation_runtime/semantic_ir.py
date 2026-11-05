"""Bounded source-observation graph: structural typing, never canonical APX parity."""
from hashlib import sha256
from copy import deepcopy
from .common import canonical,fingerprint,identity
from .preservation import observation

SCHEMA="qualityrag.source-observation-graph/v1"
DRAFT_KEYS={"observation_id","quote_start","quote_end","kind","value","roles","polarity","quantity","unit","temporal_order","modality"}


def build(raw,drafts):
    if not isinstance(raw,bytes) or not 0<len(raw)<=65536:raise ValueError("Bounded original UTF-8 source required")
    raw.decode("utf-8")
    if not isinstance(drafts,list) or not 1<=len(drafts)<=128:raise ValueError("Bounded observation inventory required")
    nodes={}
    for draft in drafts:
        if not isinstance(draft,dict) or set(draft)!=DRAFT_KEYS:raise ValueError("Complete typed observation draft required")
        if type(draft["value"]) not in (str,int,float,bool,type(None)):raise ValueError("Scalar observation value required")
        if isinstance(draft["value"],str) and len(draft["value"])>4096:raise ValueError("Observation value budget")
        node=observation(raw,**draft)
        if node["id"] in nodes:raise ValueError("Duplicate observation ID")
        nodes[node["id"]]=node
    joins=[];edges=set()
    for name,node in nodes.items():
        kind=node["kind"];roles=node["roles"];order=node["temporal_order"]
        if kind in {"ENTITY","UNKNOWN"} and (roles or order):raise ValueError("Entity/unknown nodes cannot assert joins or event order")
        if kind=="RELATION" and (set(roles)!={"subject","object"} or order):raise ValueError("Binary relation requires exactly two entity endpoints")
        if kind!="EVENT" and order:raise ValueError("Only events declare temporal antecedents")
        for role,target in roles.items():
            if target not in nodes or nodes[target]["kind"]!="ENTITY":raise ValueError("Role endpoint must resolve to a declared entity")
            joins.append({"owner":name,"role":role,"target":target,"target_kind":"ENTITY"})
        for target in order:
            if target==name or target not in nodes or nodes[target]["kind"]!="EVENT":raise ValueError("Temporal endpoint must resolve to a distinct event")
            edges.add((target,name))
        edges.update(zip(order,order[1:]))
    # Kahn traversal avoids recursion and bounds cycle checks to the finite inventory.
    indegree={name:0 for name in nodes};successors={name:set() for name in nodes}
    for before,after in edges:successors[before].add(after);indegree[after]+=1
    ready=sorted(name for name in nodes if indegree[name]==0);visited=0
    while ready:
        name=ready.pop();visited+=1
        for target in sorted(successors[name]):
            indegree[target]-=1
            if indegree[target]==0:ready.append(target)
    if visited!=len(nodes):raise ValueError("Cyclic declared temporal order")
    unknowns=[{"observation_id":name,"aspects":[field for field in ("kind","polarity","modality","value") if nodes[name][field] in ("UNKNOWN",None)]}
              for name in sorted(nodes)]
    body={"schema":SCHEMA,"source":{"sha256":sha256(raw).hexdigest(),"bytes":len(raw),"encoding":"UTF-8","residual":"RETAIN_FULL_ORIGINAL"},
          "nodes":[nodes[name] for name in sorted(nodes)],"joins":sorted(joins,key=lambda j:(j["owner"],j["role"],j["target"])),
          "temporal_edges":[{"before":a,"after":b} for a,b in sorted(edges)],"unknowns":[row for row in unknowns if row["aspects"]],
          "type_status":"WELL_TYPED","domain_validity":"UNKNOWN","canonical_apx_parity":"NOT_ESTABLISHED","can_generate":False}
    result={**body,"ast_sha256":fingerprint(body)}
    from .contracts import validate
    validate("observation-graph",result)
    return result


def _draft(node):
    return {"observation_id":node["id"],"quote_start":node["source"]["char_start"],"quote_end":node["source"]["char_end"],
            **{key:deepcopy(node[key]) for key in ("kind","value","roles","polarity","quantity","unit","temporal_order","modality")}}


def check(raw,ast):
    try:
        if not isinstance(ast,dict) or ast.get("schema")!=SCHEMA or not isinstance(ast.get("nodes"),list) or not 1<=len(ast["nodes"])<=128:raise ValueError("Typed observation graph required")
        expected=build(raw,[_draft(node) for node in ast["nodes"]])
        if canonical(ast)!=canonical(expected):raise ValueError("Source anchor, graph inventory or AST fingerprint mismatch")
        return expected
    except (KeyError,TypeError,IndexError) as exc:raise ValueError("Malformed observation graph") from exc


def rename(raw,ast,mapping):
    ast=check(raw,ast);ids={node["id"] for node in ast["nodes"]}
    if not isinstance(mapping,dict) or set(mapping)!=ids:raise ValueError("Total observation ID mapping required")
    for value in mapping.values():identity(value)
    if len(set(mapping.values()))!=len(ids):raise ValueError("Bijective observation ID mapping required")
    drafts=[]
    for node in ast["nodes"]:
        draft=_draft(node);draft["observation_id"]=mapping[node["id"]]
        draft["roles"]={role:mapping[target] for role,target in node["roles"].items()}
        draft["temporal_order"]=[mapping[target] for target in node["temporal_order"]]
        drafts.append(draft)
    transformed=build(raw,drafts)
    return transformed,{"operator":"BIJECTIVE_OBSERVATION_ID_RENAME/v1","source_sha256":ast["source"]["sha256"],
        "before_ast_sha256":ast["ast_sha256"],"after_ast_sha256":transformed["ast_sha256"],"mapping_sha256":fingerprint(mapping),
        "scope":"FINITE_DECLARED_GRAPH_ONLY","domain_validity":"UNKNOWN"}


def evaluate(raw,request):
    if not isinstance(request,dict) or set(request) not in ({"observations"},{"observations","rename"}):raise ValueError("Unsupported observation graph options")
    ast=build(raw,request["observations"]);trace=None
    if "rename" in request:ast,trace=rename(raw,ast,request["rename"])
    return {"schema":"qualityrag.observation-result/v1","ast":ast,"transition":trace,"source_sha256":ast["source"]["sha256"],
            "type_status":"WELL_TYPED","domain_validity":"UNKNOWN","canonical_apx_parity":"NOT_ESTABLISHED","can_generate":False}
