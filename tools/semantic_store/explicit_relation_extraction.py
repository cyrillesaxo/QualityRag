"""Explicit-syntax relation candidate extraction and review-gated projection.

Only recognizes literal declarations of the form:
    RELATE <source_id> <RELATION> <target_id>
on a complete line in an authorized source. This is NOT a natural-language
relation reasoner or authenticated human review. Extractor does not ingest
unreviewed or rejected candidates into KnowledgeGraph.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
import sqlite3
from time import perf_counter_ns
from typing import Callable

from semantic_codex import CodexError
from store import SemanticStore, digest, canonical_bytes

SCHEMA="qualityrag.explicit-relation-extraction/v1.2"
DECL=re.compile(r"^RELATE ([A-Za-z0-9]{1,50}) ([A-Z][A-Z_]{0,47}) ([A-Za-z0-9]{1,50})$")
VERDICTS={"SUPPORTED","REJECTED","UNCERTAIN"}
MAX_CANDIDATES=100


def extract_declared_relations(sources: list[dict], *,
                               principal: str,
                               authorize_source: Callable[[str,str,str],bool]) -> dict:
    if (not isinstance(sources,list) or not 1<=len(sources)<=40
            or not principal or not callable(authorize_source)):
        raise CodexError("Finite source inventory and authorizer required")
    all_ids=set()
    for item in sources:
        if (not isinstance(item,dict) or set(item)!={"id","text"} or
                not isinstance(item["id"],str) or not item["id"].isalnum()
                or not 1<=len(item["id"])<=50 or item["id"] in all_ids
                or not isinstance(item["text"],str) or len(item["text"])>1000):
            raise CodexError("Invalid or duplicate source")
        all_ids.add(item["id"])
    # Pre-authorize every source. Partial discovery must not be advertised as complete.
    for item in sources:
        text=item["text"]
        revision=sha256(json.dumps({"text":text},sort_keys=True).encode()).hexdigest()
        if not authorize_source(principal,"regime/"+item["id"]+".json",revision):
            raise PermissionError("Source inaccessible; extraction inventory incomplete")
    candidates=[]
    invalid_declarations=[]
    start=perf_counter_ns()
    for item in sources:
        offset=0
        for number,line in enumerate(item["text"].splitlines(keepends=True),1):
            raw=line.rstrip("\r\n")
            if raw.startswith("RELATE "):
                match=DECL.fullmatch(raw)
                if not match or match.group(1) not in all_ids or match.group(3) not in all_ids:
                    invalid_declarations.append({"source_id":item["id"],"line":number,
                                                 "status":"INVALID_EXPLICIT_DECLARATION"})
                else:
                    from_id,rel,to_id=match.groups()
                    key={"from":from_id,"to":to_id,"relation":rel,
                         "evidence_source":item["id"],
                         "anchor":{"kind":"text_span","line":number,
                                   "start":offset,"end":offset+len(raw)},
                         "source_sha256":sha256(item["text"].encode()).hexdigest(),
                         "quoted_evidence":raw}
                    key["candidate_id"]=digest(key)
                    candidates.append(key)
                    if len(candidates)>MAX_CANDIDATES:
                        raise CodexError("Relation candidate budget exceeded")
            offset+=len(line)
    elapsed=(perf_counter_ns()-start)/1_000_000
    ids=[x["candidate_id"] for x in candidates]
    if len(ids)!=len(set(ids)):
        raise CodexError("Duplicate explicit relation candidates")
    return {"schema":SCHEMA,"candidates":candidates,
            "invalid_declarations":invalid_declarations,
            "extraction_ms_measured":round(elapsed,6),
            "scope":"EXPLICIT_SOURCE_DECLARATIONS_ONLY_NOT_NATURAL_LANGUAGE",
            "interpretation":"STRUCTURAL_CANDIDATE_NOT_FACT",
            "source_authenticity":"UNVERIFIED",
            "admission":"INCONCLUSIVE","can_generate":False}


def project_reviewed_relations(store: SemanticStore, extraction: dict, *,
                               sources: list[dict],
                               verdicts: list[dict],
                               principal: str,
                               authorize_source: Callable[[str,str,str],bool]) -> dict:
    """Persist only structurally valid, caller-supported candidate edges.

    Supported is a reviewer claim, NOT a verified fact. Results remain
    experimental graph candidates and cannot be used to authorize publication.
    """
    if not principal or not callable(authorize_source):
        raise PermissionError("Source authorization required")
    if (not isinstance(extraction,dict) or extraction.get("schema")!=SCHEMA
            or extraction.get("admission")!="INCONCLUSIVE"
            or extraction.get("invalid_declarations")):
        raise CodexError("Only fully parsed explicit extraction may be projected")
    reference=extract_declared_relations(sources,principal=principal,
                                        authorize_source=authorize_source)
    if digest(extraction.get("candidates"))!=digest(reference["candidates"]):
        raise CodexError("Candidate inventory has changed since extraction")
    candidates=reference["candidates"]
    if not isinstance(verdicts,list) or len(verdicts)!=len(candidates):
        raise CodexError("Every candidate requires an explicit review verdict")
    review_map={}
    for entry in verdicts:
        if (not isinstance(entry,dict) or set(entry)!={"candidate_id","verdict"}
                or entry["verdict"] not in VERDICTS
                or not isinstance(entry["candidate_id"],str)
                or entry["candidate_id"] in review_map):
            raise CodexError("Malformed, missing or repeated review")
        review_map[entry["candidate_id"]]=entry["verdict"]
    if set(review_map)!={c["candidate_id"] for c in candidates}:
        raise CodexError("Review inventory does not match candidates")
    source_ids={s["id"]:s for s in sources}
    hashes={s["id"]:sha256(json.dumps({"text":s["text"]},sort_keys=True).encode()).hexdigest()
            for s in sources}
    persisted=0
    with store.db:
        # Existing source versions and candidate nodes are intentionally
        # required. This is not a bypass around the reviewed source registry.
        for item in candidates:
            if review_map[item["candidate_id"]]!="SUPPORTED":
                continue
            for node in (item["from"],item["to"]):
                row=store.db.execute(
                    "SELECT kind FROM semantic_versions WHERE object_id=? AND revision=?",
                    ("node:"+node,hashes[node])).fetchone()
                if row is None or row[0]!="BENCHMARK_CANDIDATE":
                    raise CodexError("Missing previously indexed candidate node")
            edge_id="extracted:"+item["candidate_id"]
            previous=store.db.execute(
                "SELECT properties_json FROM semantic_edges WHERE edge_id=?",
                (edge_id,)).fetchone()
            props={"candidate_id":item["candidate_id"],
                   "source_id":item["evidence_source"],
                   "source_sha256":item["source_sha256"],
                   "anchor":item["anchor"],
                   "review":"CALLER_SUPPORTED_UNAUTHENTICATED",
                   "verification":"NOT_PERFORMED"}
            encoded=canonical_bytes(props).decode()
            if previous:
                if previous[0]!=encoded:
                    raise CodexError("Immutable candidate edge collision")
                continue
            store.db.execute(
                "INSERT INTO semantic_edges VALUES(?,?,?,?,?,?,?,?)",
                (edge_id,"KNOWLEDGE","node:"+item["from"],hashes[item["from"]],
                 "node:"+item["to"],hashes[item["to"]],
                 item["relation"],encoded))
            persisted+=1
    return {"schema":"qualityrag.review-gated-relations/v1.2",
            "candidate_count":len(candidates),
            "supported_caller_review":sum(v=="SUPPORTED" for v in review_map.values()),
            "rejected":sum(v=="REJECTED" for v in review_map.values()),
            "uncertain":sum(v=="UNCERTAIN" for v in review_map.values()),
            "edges_newly_persisted":persisted,
            "source_authenticity":"UNVERIFIED",
            "review_authentication":"UNVERIFIED",
            "graph_semantics":"UNVERIFIED_CANDIDATE_ONLY",
            "admission":"INCONCLUSIVE","can_generate":False}
