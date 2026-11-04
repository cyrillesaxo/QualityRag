"""Read-only results -> provenance-linked *candidate* graph projections.

A candidate node represents a model ranking, not a fact about the source.
Links to existing Codex records in the WITNESS layer indicate derivation,
NOT independent corroboration, semantic truth or permission to publish.
"""
from __future__ import annotations
import json
from hashlib import sha256
from typing import Callable

from semantic_codex import CodexError
from store import SemanticStore, canonical_bytes, digest
from query import query_context


def project_visual_candidates(
    store: SemanticStore, result: dict, *, principal: str,
    authorize_source: Callable[[str,str,str],bool],
    max_candidates: int = 30,
) -> dict:
    if not principal or not callable(authorize_source):
        raise PermissionError("Authenticated source authorization required")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 30:
        raise CodexError("Candidate graph budget must be 1..30")
    if (not isinstance(result,dict)
            or result.get("schema") != "qualityrag.visual-semantic-search/v0.5"
            or result.get("admission") != "INCONCLUSIVE"
            or result.get("identity_recognition") != "NOT_PERFORMED"):
        raise CodexError("Unverified visual search result required")
    hits=result.get("results")
    if not isinstance(hits,list) or len(hits)>max_candidates:
        raise CodexError("Exceeded candidate graph budget")
    scope=digest({"prompt":result.get("prompt"),"model":result.get("model_id")})
    inserted=0
    with store.db:
        for hit in hits:
            if not isinstance(hit,dict) or hit.get("match_type") != "MODEL_RANKED_VISUAL_SCENE_CANDIDATE":
                raise CodexError("Unexpected retrieval candidate type")
            sid,rev,rid=hit.get("source_id"),hit.get("revision"),hit.get("record_id")
            if not all(isinstance(x,str) and x for x in (sid,rev,rid)):
                raise CodexError("Missing source/revision/record identity")
            if not authorize_source(principal,sid,rev):
                # Never disclose protected source IDs or their content.
                raise PermissionError("Access denied to result source")
            stored=store.db.execute(
                "SELECT source_id,source_revision,kind FROM semantic_versions "
                "WHERE object_id=? AND revision=?", (rid,rev)).fetchone()
            if stored != (sid,rev,"CODEX_RECORD"):
                raise CodexError("Result is not backed by an existing source record")
            payload={
                "kind":"MODEL_RETRIEVAL_CANDIDATE",
                "model_id":result["model_id"],
                "query_fingerprint":sha256(result["prompt"].encode()).hexdigest(),
                "source_record_id":rid,
                "source_revision":rev,
                "anchor":hit["anchor"],
                "similarity":hit["similarity"],
                "verification":"NOT_PERFORMED",
                "identity_status":"UNKNOWN",
                "admission":"INCONCLUSIVE",
                "caveat":"Candidate inference; derived witness is not independent source evidence",
            }
            uid=digest({"scope":scope,"source_id":sid,"revision":rev,"record_id":rid})
            oid="visual-candidate:"+uid
            eid="visual-witness:"+uid
            existing=store.db.execute(
                "SELECT payload_sha256 FROM semantic_versions WHERE object_id=? AND revision=?",
                (oid,rev)).fetchone()
            expected=digest(payload)
            if existing:
                if existing[0]!=expected:
                    raise CodexError("Immutable visual candidate collision")
                continue
            store.db.execute(
                "INSERT INTO semantic_versions VALUES(?,?,?,?,?,?,?)",
                (oid,rev,sid,rev,"MODEL_RETRIEVAL_CANDIDATE",
                 canonical_bytes(payload).decode(),expected))
            store.db.execute(
                "INSERT INTO semantic_edges VALUES(?,?,?,?,?,?,?,?)",
                (eid,"WITNESS",oid,rev,rid,rev,"DERIVED_FROM_CODEX_RECORD",
                 canonical_bytes({"independent":False,
                                  "derivation":"MODEL_SCORE_ONLY",
                                  "verification":"NOT_PERFORMED"}).decode()))
            inserted+=1
    return {"schema":"qualityrag.visual-candidate-graph-projection/v0.6",
            "candidate_count":len(hits),"created":inserted,
            "scope":"UNVERIFIED_MODEL_PROJECTIONS_ONLY",
            "admission":"INCONCLUSIVE","can_generate":False}
