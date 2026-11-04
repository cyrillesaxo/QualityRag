"""Provider-independent PostgreSQL client for Research Memory.

Requires psycopg 3; supported on Neon and ordinary PostgreSQL. An explicit
DSN is mandatory. This is a direct private DB client, NOT a public web API.
Inserts are append-only, evidence-bound and transactional. VALIDATED requires
a host-installed verifier; plain status labels cannot authorize it.
"""
from __future__ import annotations
import json
from ledger import (
    LedgerError, KIND, EVIDENCE, ASSESSMENTS, RELATIONS, _id, _summary,
    _HASH, _utc, canon, sha, SCHEMA, apply_dependency_states,
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
           actor:str,evidence_ids:list[str],at:str|None=None,verify_validation=None):
    _id(event_id,"event");_id(claim_id,"claim");_id(actor,"actor")
    _summary(reason,"assessment reason")
    if assessment not in ASSESSMENTS:raise LedgerError("Invalid assessment")
    if (not isinstance(evidence_ids,list) or len(evidence_ids)>50 or
        len(set(evidence_ids))!=len(evidence_ids)):
        raise LedgerError("Assessment evidence IDs must be unique and bounded")
    for eid in evidence_ids:_id(eid,"evidence")
    with conn.transaction():
        # Lock a claim to prevent two writers from racing on the event chain.
        claim_row=conn.execute("SELECT claim_id,project,kind,statement,created_at,content_hash FROM research.claims WHERE claim_id=%s FOR UPDATE",(claim_id,)).fetchone()
        if not claim_row:raise LedgerError("Unknown claim")
        selected_claim=dict(zip(("claim_id","project","kind","statement","created_at","content_hash"),claim_row))
        previous=conn.execute("SELECT event_hash,observed_at,event_id FROM research.assessment_events WHERE claim_id=%s ORDER BY observed_at DESC,event_id DESC LIMIT 1",
                              (claim_id,)).fetchone()
        observed_at=at or _utc()
        if previous and (observed_at,event_id)<=(previous[1],previous[2]):
            raise LedgerError("Assessment must append after the current event-chain head")
        kinds={}
        selected=[]
        for eid in evidence_ids:
            row=conn.execute("SELECT evidence_id,kind,uri,description,content_sha256,observed_at,metadata,record_hash FROM research.evidence WHERE evidence_id=%s FOR SHARE",(eid,)).fetchone()
            if not row:raise LedgerError("Unknown evidence")
            kinds[eid]=row[1]
            selected.append(dict(zip(("evidence_id","kind","uri","description","content_sha256","observed_at","metadata","record_hash"),row)))
        if assessment=="IMPLEMENTED" and not set(kinds.values()).intersection(("CODE_COMMIT","DEPLOYMENT")):
            raise LedgerError("IMPLEMENTED requires code/deployment evidence")
        if assessment=="TESTED" and not set(kinds.values()).intersection(("CI_RUN","TEST_RESULT")):
            raise LedgerError("TESTED requires test evidence")
        if assessment=="VALIDATED":
            item=next(item for item in progress(conn)["claims"] if item["claim_id"]==claim_id)
            if item["dependency_state"]!="SATISFIED":
                raise LedgerError("Validation dependencies remain unresolved")
            if not callable(verify_validation) or not evidence_ids:
                raise LedgerError("VALIDATED requires independent host verification and evidence")
            if "REVIEW" not in kinds.values() or not set(kinds.values()).intersection({"MEASUREMENT","TEST_RESULT","OBSERVATION"}):
                raise LedgerError("Validation requires review plus observed/test evidence")
            try:
                verified=verify_validation(selected_claim,selected) is True
            except Exception as exc:
                raise LedgerError("Independent validation refused") from exc
            if not verified:raise LedgerError("Independent validation refused")
        if assessment in ("REFUTED","SUPERSEDED") and not evidence_ids:
            raise LedgerError("Refutation/supersession requires evidence")
        prev=previous[0] if previous else None
        payload={"event_id":event_id,"claim_id":claim_id,"assessment":assessment,
                 "reason":reason.strip(),"actor":actor,"evidence_ids":evidence_ids,
                 "observed_at":observed_at,"previous_event_hash":prev}
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
    rows=conn.execute(query+" ORDER BY claim_id").fetchall()
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
    apply_dependency_states(items)
    if project is not None:items=[item for item in items if item["project"]==project]
    return {"schema":SCHEMA,"claims":items,
            "counts":{"total":len(items),"by_status":{
                s:sum(x["status"]==s for x in items) for s in sorted(ASSESSMENTS)},
                "by_effective_status":{s:sum(x["effective_status"]==s for x in items) for s in sorted(ASSESSMENTS)}},
            "source_authenticity":"UNVERIFIED_UNLESS_EXTERNALLY_ATTESTED",
            "independent_validation":"HOST_VERIFIER_REQUIRED_PER_VALIDATED_EVENT"}


def verify_integrity(conn):
    """Check stored preimages and event chains; database owners remain trusted."""
    issues=[]
    for row in conn.execute("SELECT claim_id,project,kind,statement,created_at,content_hash FROM research.claims"):
        payload=dict(zip(("claim_id","project","kind","statement","created_at"),row[:-1]))
        if sha(payload)!=row[-1]:issues.append("claim_hash:"+row[0])
    for row in conn.execute("SELECT evidence_id,kind,uri,description,content_sha256,observed_at,metadata,record_hash FROM research.evidence"):
        payload=dict(zip(("evidence_id","kind","uri","description","content_sha256","observed_at","metadata"),row[:-1]))
        if sha(payload)!=row[-1]:issues.append("evidence_hash:"+row[0])
    previous={}
    for row in conn.execute("SELECT event_id,claim_id,assessment,reason,observed_at,actor,evidence_ids,previous_event_hash,event_hash FROM research.assessment_events ORDER BY claim_id,observed_at,event_id"):
        payload=dict(zip(("event_id","claim_id","assessment","reason","observed_at","actor","evidence_ids","previous_event_hash"),row[:-1]))
        if payload["previous_event_hash"]!=previous.get(row[1]) or sha(payload)!=row[-1]:issues.append("event_chain:"+row[0])
        previous[row[1]]=row[-1]
    for row in conn.execute("SELECT link_id,from_claim,to_claim,relation,created_at,link_hash FROM research.claim_links"):
        payload=dict(zip(("link_id","from_claim","to_claim","relation","created_at"),row[:-1]))
        if sha(payload)!=row[-1]:issues.append("link_hash:"+row[0])
    return {"consistent":not issues,"issues":issues,"trust_boundary":"HASHES_AND_POSTGRES_TRIGGERS_NOT_EXTERNAL_ATTESTATION"}
