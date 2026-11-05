"""Append-only research provenance ledger: implementation != validation.

SQLite is the zero-service local reference implementation. An equivalent
PostgreSQL schema is in tools/research_ledger/postgresql.sql. No automatic
claims of scientific verification, source authenticity, or production
readiness arise from GitHub merges, tests, or notes.
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from datetime import datetime,timezone
from typing import Any

SCHEMA="qualityrag.research-ledger/v0.1"
KIND={"HYPOTHESIS","CAPABILITY","EXPERIMENT","DECISION"}
EVIDENCE={"CODE_COMMIT","CI_RUN","TEST_RESULT","MEASUREMENT","REVIEW","SOURCE_DOCUMENT","DEPLOYMENT","OBSERVATION"}
ASSESSMENTS={"UNVERIFIED","IMPLEMENTED","TESTED","VALIDATED","REFUTED","SUPERSEDED","INCONCLUSIVE"}
RELATIONS={"SUPPORTS","CHALLENGES","DEPENDS_ON","SUPERSEDES","QUALIFIES"}
_ID=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
_HASH=re.compile(r"^[0-9a-f]{64}$")


class LedgerError(ValueError):
    pass


def canon(x: Any) -> str:
    return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)


def sha(x: Any) -> str:
    return hashlib.sha256(canon(x).encode()).hexdigest()


def _id(value: str, label: str):
    if not isinstance(value,str) or not _ID.fullmatch(value):
        raise LedgerError("Invalid "+label+" ID")


def _summary(value: str,label: str):
    if not isinstance(value,str) or not 1<=len(value.strip())<=2000:
        raise LedgerError("Invalid "+label)


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def initialize(db: sqlite3.Connection):
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS research_claims(
      claim_id TEXT PRIMARY KEY,project TEXT NOT NULL,kind TEXT NOT NULL,
      statement TEXT NOT NULL,created_at TEXT NOT NULL,content_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS research_evidence(
      evidence_id TEXT PRIMARY KEY,kind TEXT NOT NULL,uri TEXT NOT NULL,
      description TEXT NOT NULL,content_sha256 TEXT,observed_at TEXT NOT NULL,
      metadata_json TEXT NOT NULL,record_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS research_events(
      event_id TEXT PRIMARY KEY,claim_id TEXT NOT NULL,
      assessment TEXT NOT NULL,reason TEXT NOT NULL,
      observed_at TEXT NOT NULL,actor TEXT NOT NULL,
      evidence_ids_json TEXT NOT NULL,previous_event_hash TEXT,
      event_hash TEXT NOT NULL,
      FOREIGN KEY(claim_id) REFERENCES research_claims(claim_id)
    );
    CREATE TABLE IF NOT EXISTS research_links(
      link_id TEXT PRIMARY KEY,from_claim TEXT NOT NULL,to_claim TEXT NOT NULL,
      relation TEXT NOT NULL,created_at TEXT NOT NULL,link_hash TEXT NOT NULL,
      FOREIGN KEY(from_claim) REFERENCES research_claims(claim_id),
      FOREIGN KEY(to_claim) REFERENCES research_claims(claim_id),
      CHECK(from_claim<>to_claim)
    );
    CREATE INDEX IF NOT EXISTS research_events_claim_idx ON research_events(claim_id,observed_at,event_id);
    CREATE INDEX IF NOT EXISTS research_claims_project_idx ON research_claims(project);
    CREATE TABLE IF NOT EXISTS research_validation_receipts(
      service TEXT NOT NULL,tenant TEXT NOT NULL,nonce TEXT NOT NULL,
      event_id TEXT NOT NULL UNIQUE,
      reviewer TEXT NOT NULL,context_sha256 TEXT NOT NULL,review_envelope TEXT NOT NULL,
      PRIMARY KEY(service,tenant,nonce),
      FOREIGN KEY(event_id) REFERENCES research_events(event_id) DEFERRABLE INITIALLY DEFERRED
    );
    """)
    for table in ("research_claims","research_evidence","research_events","research_links","research_validation_receipts"):
        for action in ("UPDATE","DELETE"):
            db.execute(
                f"CREATE TRIGGER IF NOT EXISTS forbid_{table}_{action.lower()} "
                f"BEFORE {action} ON {table} BEGIN "
                "SELECT RAISE(ABORT,'research ledger is append-only'); END;")


def claim(db,*,claim_id:str,project:str,kind:str,statement:str,at:str|None=None):
    _id(claim_id,"claim");_id(project,"project");_summary(statement,"statement")
    if kind not in KIND:raise LedgerError("Invalid claim kind")
    payload={"claim_id":claim_id,"project":project,"kind":kind,"statement":statement.strip(),"created_at":at or _utc()}
    with db:db.execute("INSERT INTO research_claims VALUES(?,?,?,?,?,?)",
        (claim_id,project,kind,payload["statement"],payload["created_at"],sha(payload)))
    return payload


def evidence(db,*,evidence_id:str,kind:str,uri:str,description:str,
             content_sha256:str|None=None,metadata:dict|None=None,at:str|None=None):
    _id(evidence_id,"evidence");_summary(description,"description")
    if kind not in EVIDENCE:raise LedgerError("Invalid evidence kind")
    if not isinstance(uri,str) or not 1<=len(uri)<=1000 or "://" not in uri:
        raise LedgerError("Expected a retrievable provenance URI")
    if content_sha256 is not None and (not isinstance(content_sha256,str) or not _HASH.fullmatch(content_sha256)):
        raise LedgerError("Invalid evidence content SHA")
    if metadata is None:metadata={}
    if not isinstance(metadata,dict) or len(canon(metadata))>20000:raise LedgerError("Invalid metadata")
    payload={"evidence_id":evidence_id,"kind":kind,"uri":uri,
             "description":description,"content_sha256":content_sha256,
             "observed_at":at or _utc(),"metadata":metadata}
    with db:db.execute("INSERT INTO research_evidence VALUES(?,?,?,?,?,?,?,?)",
        (evidence_id,kind,uri,description,content_sha256,payload["observed_at"],
         canon(metadata),sha(payload)))
    return payload


def assess(db,*,event_id:str,claim_id:str,assessment:str,reason:str,
           actor:str,evidence_ids:list[str],at:str|None=None,verify_validation=None):
    """Serialize appends; preserve an existing caller transaction with a savepoint."""
    nested=db.in_transaction
    db.execute("SAVEPOINT research_assessment" if nested else "BEGIN IMMEDIATE")
    try:
        result=_assess_record(db,event_id=event_id,claim_id=claim_id,assessment=assessment,
            reason=reason,actor=actor,evidence_ids=evidence_ids,at=at,verify_validation=verify_validation)
        if nested:db.execute("RELEASE research_assessment")
        else:db.commit()
        return result
    except Exception:
        if nested:
            db.execute("ROLLBACK TO research_assessment")
            db.execute("RELEASE research_assessment")
        else:db.rollback()
        raise


def _assess_record(db,*,event_id,claim_id,assessment,reason,actor,evidence_ids,at,verify_validation):
    _id(event_id,"event");_id(claim_id,"claim");_id(actor,"actor")
    _summary(reason,"assessment reason")
    if assessment not in ASSESSMENTS:raise LedgerError("Invalid assessment")
    if (not isinstance(evidence_ids,list) or len(evidence_ids)>50 or
            len(set(evidence_ids))!=len(evidence_ids)):
        raise LedgerError("Assessment evidence IDs must be unique and bounded")
    for eid in evidence_ids:_id(eid,"evidence")
    if not db.execute("SELECT 1 FROM research_claims WHERE claim_id=?",(claim_id,)).fetchone():
        raise LedgerError("Unknown claim")
    row=db.execute("SELECT event_hash,observed_at,event_id FROM research_events WHERE claim_id=? ORDER BY observed_at DESC,event_id DESC LIMIT 1",(claim_id,)).fetchone()
    observed_at=at or _utc()
    if row and (observed_at,event_id)<=(row[1],row[2]):
        raise LedgerError("Assessment must append after the current event-chain head")
    previous=row[0] if row else None
    for eid in evidence_ids:
        if not db.execute("SELECT 1 FROM research_evidence WHERE evidence_id=?",(eid,)).fetchone():
            raise LedgerError("Unknown evidence")
    # Supported workflow hierarchy: a commit can prove implementation, not
    # independently validated semantics; a CI run cannot certify deployed
    # behavior or scientific validity.
    if assessment=="IMPLEMENTED" and not any(
        db.execute("SELECT kind FROM research_evidence WHERE evidence_id=?",(eid,)).fetchone()[0] in
        ("CODE_COMMIT","DEPLOYMENT") for eid in evidence_ids):
        raise LedgerError("IMPLEMENTED requires code/deployment evidence")
    if assessment=="TESTED" and not any(
        db.execute("SELECT kind FROM research_evidence WHERE evidence_id=?",(eid,)).fetchone()[0] in
        ("CI_RUN","TEST_RESULT") for eid in evidence_ids):
        raise LedgerError("TESTED requires test evidence")
    if assessment=="VALIDATED":
        item=next(item for item in progress(db)["claims"] if item["claim_id"]==claim_id)
        if item["dependency_state"]!="SATISFIED":
            raise LedgerError("Validation dependencies remain unresolved")
        # Only host-owned code can install this verifier. Never derive it from
        # source text, agent proposals or a caller-supplied boolean.
        if not callable(verify_validation) or not evidence_ids:
            raise LedgerError("VALIDATED requires independent host verification and evidence")
        selected=[]
        for eid in evidence_ids:
            row=db.execute("SELECT evidence_id,kind,uri,description,content_sha256,observed_at,metadata_json,record_hash FROM research_evidence WHERE evidence_id=?",(eid,)).fetchone()
            selected.append({"evidence_id":row[0],"kind":row[1],"uri":row[2],"description":row[3],
                "content_sha256":row[4],"observed_at":row[5],"metadata":json.loads(row[6]),"record_hash":row[7]})
        kinds={row["kind"] for row in selected}
        if "REVIEW" not in kinds or not kinds.intersection({"MEASUREMENT","TEST_RESULT","OBSERVATION"}):
            raise LedgerError("Validation requires review plus observed/test evidence")
        claim_row=db.execute("SELECT claim_id,project,kind,statement,created_at,content_hash FROM research_claims WHERE claim_id=?",(claim_id,)).fetchone()
        selected_claim=dict(zip(("claim_id","project","kind","statement","created_at","content_hash"),claim_row))
        try:
            verified=verify_validation(selected_claim,selected) is True
        except Exception as exc:
            raise LedgerError("Independent validation refused") from exc
        if not verified:raise LedgerError("Independent validation refused")
    if assessment in ("REFUTED","SUPERSEDED") and not evidence_ids:
        raise LedgerError("Refutation/supersession requires evidence")
    payload={"event_id":event_id,"claim_id":claim_id,"assessment":assessment,
             "reason":reason.strip(),"actor":actor,"evidence_ids":evidence_ids,
             "observed_at":observed_at,"previous_event_hash":previous}
    db.execute("INSERT INTO research_events VALUES(?,?,?,?,?,?,?,?,?)",
        (event_id,claim_id,assessment,payload["reason"],payload["observed_at"],actor,
         canon(evidence_ids),previous,sha(payload)))
    return payload


def link(db,*,link_id:str,from_claim:str,to_claim:str,relation:str,at:str|None=None):
    for key,value in (("link",link_id),("claim",from_claim),("claim",to_claim)):_id(value,key)
    if relation not in RELATIONS or from_claim==to_claim:raise LedgerError("Invalid claim relation")
    for key in (from_claim,to_claim):
        if not db.execute("SELECT 1 FROM research_claims WHERE claim_id=?",(key,)).fetchone():
            raise LedgerError("Unknown linked claim")
    payload={"link_id":link_id,"from_claim":from_claim,"to_claim":to_claim,
             "relation":relation,"created_at":at or _utc()}
    with db:db.execute("INSERT INTO research_links VALUES(?,?,?,?,?,?)",
                       (link_id,from_claim,to_claim,relation,payload["created_at"],sha(payload)))
    return payload


def progress(db,project:str|None=None):
    rows=db.execute("SELECT claim_id,project,kind,statement,created_at,content_hash FROM research_claims "+
                    "ORDER BY claim_id").fetchall()
    items=[]
    for id_,proj,kind,statement,created,hash_ in rows:
        all_events=db.execute("SELECT event_id,assessment,reason,observed_at,actor,evidence_ids_json,previous_event_hash,event_hash "
                              "FROM research_events WHERE claim_id=? ORDER BY observed_at,event_id",(id_,)).fetchall()
        events=[{"event_id":e[0],"assessment":e[1],"reason":e[2],"observed_at":e[3],
                 "actor":e[4],"evidence_ids":json.loads(e[5]),"previous_event_hash":e[6],
                 "event_hash":e[7]} for e in all_events]
        edges=db.execute("SELECT to_claim,relation FROM research_links WHERE from_claim=? ORDER BY link_id",(id_,)).fetchall()
        items.append({"claim_id":id_,"project":proj,"kind":kind,"statement":statement,
                      "status":events[-1]["assessment"] if events else "UNVERIFIED",
                      "events":events,"links":[{"to":e[0],"relation":e[1]} for e in edges]})
    apply_dependency_states(items)
    if project is not None:items=[item for item in items if item["project"]==project]
    return {"schema":SCHEMA,"claims":items,"counts":{"total":len(items),
            "by_status":{s:sum(x["status"]==s for x in items) for s in sorted(ASSESSMENTS)},
            "by_effective_status":{s:sum(x["effective_status"]==s for x in items) for s in sorted(ASSESSMENTS)}},
            "source_authenticity":"UNVERIFIED_UNLESS_EXTERNALLY_ATTESTED",
            "independent_validation":"HOST_VERIFIER_REQUIRED_PER_VALIDATED_EVENT"}


def apply_dependency_states(items):
    """Conservative fixed point: unreviewed roots and cycles never become validated."""
    from collections import defaultdict,deque
    by_id={item["claim_id"]:item for item in items}
    dependencies={cid:{edge["to"] for edge in item["links"] if edge["relation"]=="DEPENDS_ON"}
                  for cid,item in by_id.items()}
    pending={cid:len(targets) for cid,targets in dependencies.items()}
    reverse=defaultdict(set)
    for cid,targets in dependencies.items():
        for target in targets:reverse[target].add(cid)
    ready=deque(cid for cid in by_id if by_id[cid]["status"]=="VALIDATED" and pending[cid]==0)
    safe=set()
    while ready:
        cid=ready.popleft();safe.add(cid)
        for dependent in reverse[cid]:
            pending[dependent]-=1
            if pending[dependent]==0 and by_id[dependent]["status"]=="VALIDATED":ready.append(dependent)
    for cid,item in by_id.items():
        blockers=sorted(dependencies[cid]-safe)
        item["dependency_state"]="UNRESOLVED" if blockers else "SATISFIED"
        item["dependency_blockers"]=blockers
        item["effective_status"]=("INCONCLUSIVE" if item["status"]=="VALIDATED" and cid not in safe else item["status"])
    return items


def dependency_context(items,claim_id):
    """Bind review to every transitive prerequisite, including head and graph changes."""
    by_id={item["claim_id"]:item for item in items}
    def targets(item):return sorted({e["to"] for e in item["links"] if e["relation"]=="DEPENDS_ON"})
    pending=targets(by_id[claim_id]);seen=set();result=[]
    while pending:
        cid=pending.pop()
        if cid in seen:continue
        seen.add(cid)
        item=by_id.get(cid)
        if item is None:
            result.append({"claim_id":cid,"status":"MISSING"});continue
        edges=targets(item);pending.extend(edges)
        result.append({"claim_id":cid,"status":item["status"],"effective_status":item["effective_status"],
                       "head":item["events"][-1]["event_hash"] if item["events"] else None,"dependencies":edges})
    return sorted(result,key=lambda item:item["claim_id"])


def verify_integrity(db):
    """Detect accidental row corruption; NOT a defense against DBA rewrite."""
    issues=[]
    for id_,project,kind,statement,at,h in db.execute("SELECT * FROM research_claims"):
        if sha({"claim_id":id_,"project":project,"kind":kind,"statement":statement,"created_at":at})!=h:
            issues.append("claim_hash:"+id_)
    for row in db.execute("SELECT * FROM research_evidence"):
        id_,kind,uri,description,content_sha256,at,metadata,h=row
        payload={"evidence_id":id_,"kind":kind,"uri":uri,"description":description,
                 "content_sha256":content_sha256,"observed_at":at,"metadata":json.loads(metadata)}
        if sha(payload)!=h:issues.append("evidence_hash:"+id_)
    for claim_id, in db.execute("SELECT claim_id FROM research_claims"):
        prev=None
        rows=db.execute("SELECT * FROM research_events WHERE claim_id=? ORDER BY observed_at,event_id",(claim_id,)).fetchall()
        for row in rows:
            id_,cid,assessment,reason,at,actor,evidence_ids,previous,event_hash=row
            payload={"event_id":id_,"claim_id":cid,"assessment":assessment,"reason":reason,
                     "actor":actor,"evidence_ids":json.loads(evidence_ids),
                     "observed_at":at,"previous_event_hash":previous}
            if previous!=prev or sha(payload)!=event_hash:issues.append("event_chain:"+id_)
            prev=event_hash
    for id_,fr,to,relation,at,h in db.execute("SELECT * FROM research_links"):
        if sha({"link_id":id_,"from_claim":fr,"to_claim":to,"relation":relation,"created_at":at})!=h:
            issues.append("link_hash:"+id_)
    return {"consistent":not issues,"issues":issues,
            "trust_boundary":"HASHES_AND_SQLITE_TRIGGERS_NOT_EXTERNAL_ATTESTATION"}

