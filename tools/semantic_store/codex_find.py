"""Finite, source-anchored lookup across inspected Semantic Codex records.

Lexical FIND over extracted scalar fields, including WebVTT captions. Not
visual person recognition, semantic similarity, OCR or full-text indexing.
"""
from __future__ import annotations
import re
from typing import Any
from semantic_codex import CodexError, SCHEMA
from store import digest

def find_text(
    artifacts: list[dict[str, Any]], term: str, *,
    authorize_source, principal: str, max_hits: int = 100
) -> dict:
    if (not isinstance(principal,str) or not principal.strip()
            or not callable(authorize_source)):
        raise PermissionError("Authenticated caller and source authorization required")
    if (not isinstance(term,str) or not 1<=len(term.strip())<=128
            or not isinstance(artifacts,list) or len(artifacts)>50
            or type(max_hits) is not int or not 1<=max_hits<=100):
        raise CodexError("Search input exceeds finite limits")
    needle=term.casefold()
    hits=[]
    truncated=False
    searched=0
    for artifact in artifacts:
        if not isinstance(artifact,dict):
            raise CodexError("Invalid artifact")
        body=dict(artifact)
        fingerprint=body.pop("fingerprint",None)
        if body.get("schema")!=SCHEMA or fingerprint!=digest(body):
            raise CodexError("Tampered Codex artifact")
        source=artifact["source"]
        if not authorize_source(principal,source["source_id"],source["revision"]):
            continue
        searched+=1
        for record in artifact["records"]:
            for field,value in record["fields"].items():
                # Only lexical TEXT values, not nontext values or inferred names.
                if value["type"]=="TEXT" and needle in value["value"].casefold():
                    if len(hits)>=max_hits:
                        truncated=True
                        break
                    hits.append({"source_id":source["source_id"],"revision":source["revision"],
                                 "format":source["format"],"source_sha256":source["sha256"],
                                 "record_id":record["id"],"anchor":record["anchor"],
                                 "field":field,"matched_text":value["value"],
                                 "match_type":"LEXICAL_EXTRACTED_TEXT",
                                 "verification":"NOT_PERFORMED"})
            if truncated:
                break
        if truncated:
            break
    return {"schema":"qualityrag.semantic-codex-search/v0.1",
            "term":term,"hits":hits,"searched_authorized_sources":searched,
            "truncated":truncated,"source_coverage":"ONLY_SUPPLIED_COMPILED_ARTIFACTS",
            "visual_identity_recognition":"NOT_PERFORMED",
            "admission":"INCONCLUSIVE","can_generate":False}
