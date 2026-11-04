"""Bounded Gardener suggestions and outcome metrics; no autonomous truth promotion."""
from pathlib import Path
from time import perf_counter_ns
from .gardener import Gardener
from .common import fingerprint


def suggest(path,*,limit=20):
    if type(limit) is not int or not 1<=limit<=100:raise ValueError("Proposal count budget")
    garden=Gardener(path)
    start=perf_counter_ns()
    try:
        state=garden.replay()
        if len(state["events"])>2000:raise ValueError("Proposal scan budget exceeded")
        by_source={}
        output=[]
        for event in state["events"].values():
            if event["operation"] not in {"PROPOSE","SYNTHESIZE"} or not state["branches"][event["branch"]]["active"]:continue
            key=(event["source_sha256"],event["statement"].strip().casefold())
            if key in by_source:
                previous=by_source[key]
                output.append({"id":fingerprint([previous["event_id"],event["event_id"]]),
                    "kind":"POSSIBLE_DUPLICATE","branches":[previous["branch"],event["branch"]],
                    "source_sha256":event["source_sha256"],"source_ref":event["source_ref"],
                    "confidence":None,"calibration":"UNMEASURED","suggested_operation":"PRUNE",
                    "review_required":True,"reversible":True})
            else:by_source[key]=event
            if len(output)>=limit:break
        for branch,info in state["branches"].items():
            challenges=[state["events"][eid] for eid in info["events"] if state["events"][eid]["operation"]=="CHALLENGE"]
            if challenges and len(output)<limit:
                event=challenges[-1]
                output.append({"id":fingerprint([branch,event["event_id"]]),"kind":"UNRESOLVED_CHALLENGE",
                    "branches":[branch],"source_sha256":event["source_sha256"],"source_ref":event["source_ref"],
                    "confidence":None,"calibration":"UNMEASURED","suggested_operation":"TEST",
                    "review_required":True,"reversible":True})
        _outcome_schema(garden.db)
        with garden.db:
            for proposal in output:
                garden.db.execute("INSERT OR IGNORE INTO gardener_proposal_candidates VALUES(?,?)",
                                  (proposal["id"],__import__("json").dumps(proposal,sort_keys=True)))
        return {"schema":"qualityrag.gardener-proposals/v1","proposals":output,
                "metrics":outcome_metrics(path,state),
                "scan_ns":perf_counter_ns()-start,"scanned_events":len(state["events"]),
                "automatic_promotions":0,"false_merge_rate":None,"utility":"REQUIRES_REVIEW_OUTCOMES"}
    finally:garden.close()


def dependency_evidence(state):
    """Synthesis never upgrades unresolved ancestors; uncertainty propagates."""
    result={}
    def visit(branch):
        if branch in result:return result[branch]
        parents=state["branches"][branch]["parents"]
        unresolved=[p for p in parents if visit(p)!="VALIDATED"]
        result[branch]="UNRESOLVED_DEPENDENCIES" if unresolved else "UNVERIFIED"
        return result[branch]
    for branch in state["branches"]:visit(branch)
    return result


def record_outcome(path,*,proposal_id,actor,verdict,useful,elapsed_ms,false_merge):
    """Authenticated application supplies actor; feedback remains reviewer-reported."""
    from .common import identity
    identity(actor)
    if verdict not in {"CONFIRMED","INCORRECT","UNRESOLVED"} or type(useful) is not bool or type(false_merge) is not bool or type(elapsed_ms) is not int or not 0<=elapsed_ms<=86400000:
        raise ValueError("Typed bounded review outcome required")
    import sqlite3
    with sqlite3.connect(path) as db:
        _outcome_schema(db)
        if not db.execute("SELECT 1 FROM gardener_proposal_candidates WHERE id=?",(proposal_id,)).fetchone():
            raise ValueError("Unknown source-linked proposal")
        db.execute("INSERT INTO gardener_proposal_outcomes VALUES(?,?,?,?,?,?,?)",
                   (proposal_id,actor,verdict,int(useful),elapsed_ms,int(false_merge),"REVIEWER_REPORTED"))
    return {"recorded":True,"evidence_class":"REVIEWER_REPORTED_NOT_INDEPENDENT_VALIDATION"}


def _outcome_schema(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS gardener_proposal_candidates(id TEXT PRIMARY KEY,body TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS gardener_proposal_outcomes(
      proposal_id TEXT NOT NULL,actor TEXT NOT NULL,verdict TEXT NOT NULL,useful INTEGER NOT NULL,
      elapsed_ms INTEGER NOT NULL,false_merge INTEGER NOT NULL,evidence_class TEXT NOT NULL,
      PRIMARY KEY(proposal_id,actor));
    CREATE TRIGGER IF NOT EXISTS outcomes_no_update BEFORE UPDATE ON gardener_proposal_outcomes
      BEGIN SELECT RAISE(ABORT,'append-only'); END;
    CREATE TRIGGER IF NOT EXISTS outcomes_no_delete BEFORE DELETE ON gardener_proposal_outcomes
      BEGIN SELECT RAISE(ABORT,'append-only'); END;
    """)


def outcome_metrics(path,state):
    import sqlite3
    with sqlite3.connect(path) as db:
        _outcome_schema(db)
        rows=db.execute("SELECT verdict,useful,elapsed_ms,false_merge FROM gardener_proposal_outcomes").fetchall()
    evaluated=[r for r in rows if r[0]!="UNRESOLVED"]
    changes=sum(e["operation"] in {"PRUNE","REOPEN"} for e in state["events"].values())
    return {"reviews":len(rows),"false_merge_rate":sum(r[3] for r in rows)/len(rows) if rows else None,
            "incorrect_suggestion_rate":sum(r[0]=="INCORRECT" for r in evaluated)/len(evaluated) if evaluated else None,
            "reported_useful_rate":sum(r[1] for r in rows)/len(rows) if rows else None,
            "review_time_ms":sum(r[2] for r in rows),"branch_churn":changes/max(1,len(state["branches"])),
            "cost_usd":None,"evidence_class":"REVIEWER_REPORTED_AND_EVENT_COUNTS"}
