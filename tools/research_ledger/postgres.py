"""Provider-independent PostgreSQL client for Research Memory.

Requires psycopg 3; supported on Neon and ordinary PostgreSQL. An explicit
DSN is mandatory. This is a direct private DB client, NOT a public web API.
Inserts are append-only, evidence-bound and transactional. VALIDATED remains
blocked until independent verification is implemented.
"""
from __future__ import annotations
import json
from ledger import (
    LedgerError, KIND, EVIDENCE, ASSESSMENTS, RELATIONS, _id, _summary,
    _HASH, _utc, canon, sha, SCHEMA,
)


def connect(dsn: str):
    if not isinstance(dsn,str) or not dsn.strip():
        raise LedgerError("Explicit PostgreSQL connection required")
    try:
        import psycopg
    except ImportError as exc:
        raise LedgerError("Install psycopg[binary] to use PostgreSQL") from exc
    return psycopg.connect(dsn, autocommit=False)


def claim(conn, *, claim_id:str, project:str, kind:str, statement:str, at:str|None=None):
    _id(claim_id,"claim");_id(project,"project");_summary(statement,"statement")
    if kind not in KIND:raise LedgerError("Invalid claim kind")
    payload={"claim_id":claim_id,"project":project,"kind":kind,"statement":statement.strip(),"created_at":at or _utc()}
    with conn.transaction():
        conn.execute("INSERT INTO research.claims (claim_id,project,kind,statement,created_at,content_hash) VALUES (%s,%s,%s,%s,%s,%s)",
                     (claim_id,project,kind,payload["statement"],payload["created_at"],sha(payload)))
    return payload


def evidence(conn,*,evidence_id:str,kind:str,uri:str,description:str,
             content_sha256:str|None=None,metadata:dict|None=None,at:str|None=None):
    _id(evidence_id,"evidence");_summary(description,"description")
    if kind not in EVIDENCE:raise LedgerError("Invalid evidence kind")
    if not isinstance(uri,str) or not 1<=len(uri)<=1000 or "://" not in uri:
        raise LedgerError("Expected a retrievable provenance URI")
    if content_sha256 is not None and (not isinstance(content_sha256,str) or not _HASH.fullmatch(content_sha256)):
        raise LedgerError("Invalid evidence content SHA")
    metadata={} if metadata is None else metadata
    if not isinstance(metadata,dict) or len(canon(metadata))>20000:
        raise LedgerError("Invalid metadata")
    payload={"evidence_id":evidence_id,"kind":kind,"uri":uri,
             "description":description,"content_sha256":content_sha256,
             "observed_at":at or _utc(),"metadata":metadata}
    with conn.transaction():
        conn.execute("INSERT INTO research.evidence (evidence_id,kind,uri,description,content_sha256,observed_at,metadata,record_hash) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                     (evidence_id,kind,uri,description,content_sha256,payload["observed_at"],
                      canon(metadata),sha(payload)))
    return payload


def assess(conn,*,event_id:str,claim_id:str,assessment:str,reason:str,
           actor:str,evidence_ids:list[str],at:str|None=None):
    _id(event_id,"event");_id(claim_id,"claim");_id(actor,"actor")
    _summary(reason,"assessment reason")
    if assessment not in ASSESSMENTS:raise LedgerError("Invalid assessment")
    if (not isinstance(evidence_ids,list) or len(evidence_ids)>50 or
        len(set(evidence_ids))!=len(evidence_ids)):
        raise LedgerError("Assessment evidence IDs must be unique and bounded")
    for eid in evidence_ids:_id(eid,"evidence")
    with conn.transaction():
        # Lock a claim to prevent two writers from racing on the event chain.
        exists=conn.execute("SELECT 1 FROM research.claims WHERE claim_id=%s FOR UPDATE",(claim_id,)).fetchone()
        if not exists:raise LedgerError("Unknown claim")
        kinds={}
        for eid in evidence_ids:
            row=conn.execute("SELECT kind FROM research.evidence WHERE evidence_id=%s",(eid,)).fetchone()
            if not row:raise LedgerError("Unknown evidence")
            kinds[eid]=row[0]
        if assessment=="IMPLEMENTED" and not set(kinds.values()).intersection(("CODE_COMMIT","DEPLOYMENT")):
            raise LedgerError("IMPLEMENTED requires code/deployment evidence")
        if assessment=="TESTED" and not set(kinds.values()).intersection(("CI_RUN","TEST_RESULT")):
            raise LedgerError("TESTED requires test evidence")
        if assessment=="VALIDATED":
            raise LedgerError("Independent validation integration not implemented")
        if assessment in ("REFUTED","SUPERSEDED") and not evidence_ids:
            raise LedgerError("Refutation/supersession requires evidence")
        previous=conn.execute("SELECT event_hash FROM research.assessment_events WHERE claim_id=%s ORDER BY observed_at DESC,event_id DESC LIMIT 1",
                              (claim_id,)).fetchone()
        prev=previous[0] if previous else None
        payload={"event_id":event_id,"claim_id":claim_id,"assessment":assessment,
                 "reason":reason.strip(),"actor":actor,"evidence_ids":evidence_ids,
                 "observed_at":at or _utc(),"previous_event_hash":prev}
        conn.execute("INSERT INTO research.assessment_events (event_id,claim_id,assessment,reason,observed_at,actor,evidence_ids,previous_event_hash,event_hash) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
                     (event_id,claim_id,assessment,payload["reason"],payload["observed_at"],
                      actor,canon(evidence_ids),prev,sha(payload)))
    return payload


def link(conn,*,link_id:str,from_claim:str,to_claim:str,relation:str,at:str|None=None):
    for label,value in (("link",link_id),("claim",from_claim),("claim",to_claim)):
        _id(value,label)
    if relation not in RELATIONS or from_claim==to_claim:raise LedgerError("Invalid claim relation")
    payload={"link_id":link_id,"from_claim":from_claim,"to_claim":to_claim,
             "relation":relation,"created_at":at or _utc()}
    with conn.transaction():
        for key in (from_claim,to_claim):
            if not conn.execute("SELECT 1 FROM research.claims WHERE claim_id=%s",(key,)).fetchone():
                raise LedgerError("Unknown linked claim")
        conn.execute("INSERT INTO research.claim_links (link_id,from_claim,to_claim,relation,created_at,link_hash) VALUES (%s,%s,%s,%s,%s,%s)",
                     (link_id,from_claim,to_claim,relation,payload["created_at"],sha(payload)))
    return payload


def progress(conn,project:str|None=None):
    query="SELECT claim_id,project,kind,statement FROM research.claims"
    args=()
    if project is not None:
        query+=" WHERE project=%s"
        args=(project,)
    rows=conn.execute(query+" ORDER BY claim_id",args).fetchall()
    items=[]
    for cid,proj,kind,statement in rows:
        events=[]
        for event_id,assessment,reason,observed_at,actor,evidence_ids,previous,event_hash in conn.execute(
                "SELECT event_id,assessment,reason,observed_at,actor,evidence_ids,previous_event_hash,event_hash "
                "FROM research.assessment_events WHERE claim_id=%s ORDER BY observed_at,event_id",(cid,)):
            events.append({"event_id":event_id,"assessment":assessment,
                           "reason":reason,"observed_at":observed_at,"actor":actor,
                           "evidence_ids":evidence_ids,"previous_event_hash":previous,
                           "event_hash":event_hash})
        links=[{"to":dest,"relation":relation} for dest,relation in conn.execute(
            "SELECT to_claim,relation FROM research.claim_links WHERE from_claim=%s ORDER BY link_id",(cid,))]
        items.append({"claim_id":cid,"project":proj,"kind":kind,"statement":statement,
                      "status":events[-1]["assessment"] if events else "UNVERIFIED",
                      "events":events,"links":links})
    return {"schema":SCHEMA,"claims":items,
            "counts":{"total":len(items),"by_status":{
                s:sum(x["status"]==s for x in items) for s in sorted(ASSESSMENTS)}},
            "source_authenticity":"UNVERIFIED_UNLESS_EXTERNALLY_ATTESTED",
            "independent_validation":"NOT_IMPLEMENTED"}
