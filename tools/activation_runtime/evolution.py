"""Persistent feedback-driven RCT research growth. No automatic production release.

Each invocation is bounded; --continuous repeats within durable budget.
Without fresh evaluation families, growth is development-only. Ollama is host configured, never chosen by a proposal.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime,timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request,build_opener,HTTPRedirectHandler

from .common import canonical,fingerprint,identity,strict_json
from .artifacts import ArtifactStore
from .gardener import Gardener,ledger
from .evolution_program import validate,MAX_SOURCE

SCHEMA="qualityrag.evolution-config/v1"


def source_bytes(path):
    with Path(path).open("rb") as stream:raw=stream.read(MAX_SOURCE+1)
    if not 0<len(raw)<=MAX_SOURCE:raise ValueError("Source byte budget")
    return raw


def engine_pin():
    return {name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("evolution.py","evolution_worker.py","evolution_program.py","process_sandbox.py","gardener.py","common.py")}


def status(path):
    path=Path(path).resolve()
    if not path.is_file():return {"status":"NOT_STARTED","can_release":False}
    import sqlite3
    with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='evolution_cycles'").fetchone():
            return {"status":"NOT_STARTED","can_release":False}
        budget=db.execute("SELECT limit_units,spent FROM evolution_budget WHERE id=1").fetchone()
        cycles=[{"cycle":row[0],"stage":row[1]} for row in db.execute("SELECT id,stage FROM evolution_cycles ORDER BY id DESC LIMIT 20")]
        champions=[{"packspec_sha256":r[0],"branch":r[1],"program_sha256":fingerprint(json.loads(r[2]))}
                   for r in db.execute("SELECT contract_sha,branch,program FROM evolution_champions ORDER BY contract_sha")]
    return {"status":"RECORDED_RESEARCH_STATE","cycles":cycles,"champions":champions,
            "budget":{"limit_units":budget[0],"reserved_units":budget[1]},
            "worker_running":"NOT_INFERRED_FROM_HISTORY","can_release":False,"can_generate":False}


class OllamaProposer:
    def __init__(self,model,endpoint="http://127.0.0.1:11434/api/chat"):
        from urllib.parse import urlsplit
        url=urlsplit(endpoint)
        if url.scheme not in {"http","https"} or not url.hostname or url.username or url.password:
            raise ValueError("Host-owned Ollama endpoint required")
        self.model=model;self.endpoint=endpoint

    def propose(self,context):
        if len(canonical(context))>65536:raise ValueError("Planning context byte budget exceeded")
        instructions=("You are the Semantic Garden grammar/activation research agent. Read prior failures and lineage. "
            "Return JSON with candidates (1-4), each containing hypothesis, parents (existing branch IDs, 0-2), and program. "
            "Program schema is qualityrag.reversible-grammar/v1, rules is a compositional list (1-8): "
            "{op:zlib,level:1..9}, {op:bz2,level:1..9}, {op:delta,stride:1..4096}, "
            "{op:xor,value:0..255}, {op:reverse}. Activation is {mode:ON_DEMAND or EAGER,chunk_bytes:256..262144}. "
            "Learn reusable source-bound nonterminals using {op:productions,rules:[{name:identifier,literal:training-source-text}]}, "
            "1-32 unique productions of at most 256 UTF-8 bytes each; literals must occur in the training source. "
            "Compose new grammar programs and activation plans from observed counterexamples, not a fixed candidate grid. "
            "Do not request held-out data, invent measurements, execute code, or claim semantic validation. "
            "Byte-exact preservation is mandatory. Candidates must account for all grammar and metadata bytes.")
        body={"model":self.model,"stream":False,"format":"json","options":{"num_predict":2048,"num_ctx":16384},"messages":[
            {"role":"system","content":instructions},{"role":"user","content":canonical(context).decode()}]}
        request=Request(self.endpoint,data=canonical(body),headers={"Content-Type":"application/json"})
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        with build_opener(NoRedirect()).open(request,timeout=45) as response:raw=response.read(524289)
        result=strict_json(raw)
        if result.get("done") is not True:raise ValueError("Provider did not finish the recorded request")
        proposals=strict_json(result["message"]["content"].encode())
        return {"candidates":proposals["candidates"],"provider":{"backend":"OLLAMA","requested_model":self.model,"reported_model":result.get("model"),
                "reported_input_tokens":result.get("prompt_eval_count"),"reported_output_tokens":result.get("eval_count"),
                "reported_duration_ns":result.get("total_duration"),"usd":"UNMEASURED"}}


def experiment(raw,program,*,decoder_install_bytes=None):
    start=time.perf_counter_ns()
    code={name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("evolution.py","evolution_worker.py","evolution_program.py","process_sandbox.py")}
    request={"source":base64.b64encode(raw).decode(),"program":program,"code_sha256":code,"python_version":sys.version,
             "decoder_install_bytes":decoder_install_bytes}
    result=subprocess.run([sys.executable,str(Path(__file__).with_name("evolution_worker.py"))],
        input=canonical(request),capture_output=True,timeout=8,check=False,
        env={"PATH":os.environ.get("PATH","/usr/bin:/bin")},close_fds=True)
    if result.returncode or len(result.stdout)>4_000_000:raise ValueError("Resource/grammar/fidelity refusal")
    receipt=strict_json(result.stdout,max_bytes=4_000_000)
    if (receipt["source_sha256"]!=sha256(raw).hexdigest() or receipt["output_sha256"]!=sha256(raw).hexdigest()
            or receipt["finite_constraint_result"]!="SAT" or receipt["selected_bytes"]>len(raw)):
        raise ValueError("Unqualified experiment receipt")
    payload=base64.b64decode(receipt.pop("selected_payload"),validate=True)
    if len(payload)!=receipt["payload_bytes"] or (receipt["fallback"] and payload!=raw):
        raise ValueError("Delivery floor failed")
    receipt["experiment_wall_ns"]=time.perf_counter_ns()-start
    if any(sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()!=digest for name,digest in code.items()):
        raise ValueError("Evaluator changed during experiment")
    for field in ("activation","verification"):
        trace=receipt[field].pop("activation_trace")
        receipt[field].update(trace_sha256=fingerprint(trace),trace_preview=trace[:16],steps=len(trace))
    receipt["code_sha256"]=code
    receipt["python_version"]=sys.version
    return receipt,payload


class EvolutionGarden:
    def __init__(self,path,config,*,work_limit=200,clock=None,public_contract_store=None):
        self.path=Path(path).resolve();self.path.parent.mkdir(parents=True,exist_ok=True)
        self.config,self.source_digests=self._config(config);self.contract_sha=fingerprint(config["packspec"])
        if type(work_limit) is not int or not 1<=work_limit<=100000:raise ValueError("Durable work budget")
        self.clock=clock or (lambda:datetime.now(timezone.utc).isoformat())
        self.store=ArtifactStore(self.path.parent/"evolution-objects",tenant="research")
        self.store.put(canonical(config["packspec"]))
        if public_contract_store is not None:
            if not isinstance(public_contract_store,ArtifactStore):raise ValueError("Host-owned public contract store required")
            public_contract_store.put(canonical(config["packspec"]))
        self.snapshots={}
        self.garden=Gardener(self.path);db=self.garden.db
        db.executescript("""
        CREATE TABLE IF NOT EXISTS evolution_budget(id INTEGER PRIMARY KEY CHECK(id=1),limit_units INTEGER,spent INTEGER);
        CREATE TABLE IF NOT EXISTS evolution_cycles(id INTEGER PRIMARY KEY,contract_sha TEXT,stage TEXT,body TEXT);
        CREATE TABLE IF NOT EXISTS evolution_families(family TEXT PRIMARY KEY,cycle_id INTEGER);
        CREATE TABLE IF NOT EXISTS evolution_champions(contract_sha TEXT PRIMARY KEY,branch TEXT,program TEXT);
        CREATE TABLE IF NOT EXISTS evolution_sources(source_sha TEXT PRIMARY KEY,family TEXT,split TEXT);
        CREATE TABLE IF NOT EXISTS evolution_used_sources(source_sha TEXT PRIMARY KEY,cycle_id INTEGER);
        CREATE TRIGGER IF NOT EXISTS evolution_done_immutable BEFORE UPDATE ON evolution_cycles
          WHEN OLD.stage='DONE' BEGIN SELECT RAISE(ABORT,'completed research is immutable'); END;
        CREATE TRIGGER IF NOT EXISTS evolution_cycles_no_delete BEFORE DELETE ON evolution_cycles
          BEGIN SELECT RAISE(ABORT,'research history is append-only'); END;
        """)
        try:
            for row in config["sources"]:
                raw=source_bytes(row["path"]);digest=sha256(raw).hexdigest()
                if digest!=self.source_digests[row["id"]]:raise ValueError("Source changed during registration")
                self.snapshots[row["id"]]=self.store.put(raw)
                old=db.execute("SELECT family,split FROM evolution_sources WHERE source_sha=?",(digest,)).fetchone()
                if old and tuple(old)!=(row["family"],row["split"]):raise ValueError("Previously registered content cannot be relabeled across families/splits")
                db.execute("INSERT OR IGNORE INTO evolution_sources VALUES(?,?,?)",(digest,row["family"],row["split"]))
            db.execute("INSERT OR IGNORE INTO evolution_budget VALUES(1,?,0)",(work_limit,));db.commit()
        except Exception:db.rollback();self.garden.close();raise

    def close(self):self.garden.close()

    def retry_provider(self):
        """Explicit operator retry: same sealed snapshot, another charged call."""
        db=self.garden.db
        with self.path.with_suffix(".evolution.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT id FROM evolution_cycles WHERE stage='REQUESTED' ORDER BY id LIMIT 1").fetchone()
                if not row:raise ValueError("No interrupted provider request")
                limit,spent=db.execute("SELECT limit_units,spent FROM evolution_budget WHERE id=1").fetchone()
                if spent>=limit:raise ValueError("Research budget exhausted")
                db.execute("UPDATE evolution_budget SET spent=spent+1 WHERE id=1")
                db.execute("UPDATE evolution_cycles SET stage='PLANNED' WHERE id=?",(row[0],));db.commit()
            except Exception:db.rollback();raise

    @staticmethod
    def _config(config):
        if not isinstance(config,dict) or set(config)!={"schema","packspec","sources","max_candidates"} or config["schema"]!=SCHEMA:
            raise ValueError("Versioned research configuration")
        p=config["packspec"]
        if (not isinstance(p,dict) or set(p)!={"id","revision","purpose","fidelity","baseline","decoder_install_bytes"}
                or p["fidelity"]!="BYTE_EXACT" or p["baseline"] not in {"AV1_PASSTHROUGH","ORIGINAL_PASSTHROUGH"}):
            raise ValueError("Explicit byte-exact purpose contract required")
        for key in ("id","revision","purpose"):identity(p[key])
        install=p["decoder_install_bytes"]
        if install is not None and (type(install) is not int or not 0<=install<=2**53):raise ValueError("Explicit bounded runtime cost or null required")
        if type(config["max_candidates"]) is not int or not 1<=config["max_candidates"]<=4:raise ValueError("Candidate budget")
        rows=config["sources"]
        if not isinstance(rows,list) or not 3<=len(rows)<=64:raise ValueError("Bounded source inventory")
        ids=set();families={};splits=set();contents={};digests={}
        for row in rows:
            if not isinstance(row,dict) or set(row)!={"id","family","split","path","rights_ref"}:raise ValueError("Source manifest")
            for key in ("id","family"):identity(row[key])
            if row["id"] in ids or row["split"] not in {"TRAIN","DEV","EVALUATION"}:raise ValueError("Source ID or split")
            if row["family"] in families and families[row["family"]]!=row["split"]:raise ValueError("Family leakage")
            if not isinstance(row["rights_ref"],str) or not row["rights_ref"].strip():raise ValueError("Rights reference required; not verified permission")
            path=Path(row["path"])
            if not path.is_absolute() or not path.is_file() or not 0<path.stat().st_size<=MAX_SOURCE:raise ValueError("Host-owned bounded source required")
            digest=sha256(source_bytes(path)).hexdigest();digests[row["id"]]=digest
            if digest in contents and contents[digest]!=(row["family"],row["split"]):raise ValueError("Duplicate content crosses a declared family/split")
            contents[digest]=(row["family"],row["split"])
            if p["baseline"]=="AV1_PASSTHROUGH":
                probe=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_name","-of","json",str(path)],capture_output=True,timeout=10,check=True)
                streams=json.loads(probe.stdout).get("streams",[])
                if not streams or streams[0]["codec_name"]!="av1":raise ValueError("Actual AV1 baseline required")
                if sha256(source_bytes(path)).hexdigest()!=digest:raise ValueError("Source changed during AV1 validation")
            ids.add(row["id"]);families[row["family"]]=row["split"];splits.add(row["split"])
        if splits!={"TRAIN","DEV","EVALUATION"}:raise ValueError("Train/dev/fresh evaluation required")
        return json.loads(json.dumps(config)),digests

    def _event(self,cycle,suffix,operation,branch,statement,*,parents=(),evidence_ids=()):
        event_id=f"evo-{cycle}-{suffix}"
        if event_id in self.garden.replay()["events"]:return
        self.garden.append(event_id=event_id,operation=operation,branch=branch,actor="rct-evolution",
            source_sha256=self.contract_sha,source_ref="packspec:"+self.config["packspec"]["id"],
            statement=statement[:2000],at=self.clock(),parents=parents,evidence_ids=evidence_ids)

    def _save(self,cycle,stage,body):
        self.garden.db.execute("UPDATE evolution_cycles SET stage=?,body=? WHERE id=?",(stage,canonical(body).decode(),cycle));self.garden.db.commit()

    def _receipt(self,cycle,label,value):
        address=self.store.put(canonical(value));eid=f"evo-{cycle}-{label}"
        if not self.garden.db.execute("SELECT 1 FROM research_evidence WHERE evidence_id=?",(eid,)).fetchone():
            ledger.evidence(self.garden.db,evidence_id=eid,kind="TEST_RESULT",uri="sha256://"+address,content_sha256=address,
                description="Observed bounded RCT experiment; not independent domain validation",at=self.clock())
        return eid,address

    def cycle(self,proposer):
        # One owner per durable workspace, including across service processes.
        with self.path.with_suffix(".evolution.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            return self._cycle(proposer)

    def _cycle(self,proposer):
        db=self.garden.db
        pending=db.execute("SELECT id,stage,body FROM evolution_cycles WHERE stage!='DONE' ORDER BY id LIMIT 1").fetchone()
        champion=db.execute("SELECT branch,program FROM evolution_champions WHERE contract_sha=?",(self.contract_sha,)).fetchone()
        if pending:
            cycle,stage,raw=pending;body=json.loads(raw)
            if body["contract_sha256"]!=self.contract_sha:raise ValueError("Resume needs original purpose contract")
            if body["engine_pin"]!=engine_pin():raise ValueError("Pending cycle needs its original pinned evaluator checkout")
        else:
            used={r[0] for r in db.execute("SELECT family FROM evolution_families")}
            available=sorted({r["family"] for r in self.config["sources"] if r["split"]=="EVALUATION"}-used)
            family=available[0] if available else None
            selected=[r for r in self.config["sources"] if r["split"]!="EVALUATION" or r["family"]==family]
            # Snapshot exact bytes before prompting. Restart never silently tests changed files.
            sources=[]
            for row in selected:
                address=self.snapshots[row["id"]]
                sources.append({k:row[k] for k in ("id","family","split","rights_ref")} | {"source_sha256":address})
            reserve=1+2*self.config["max_candidates"]*len(sources)
            db.execute("BEGIN IMMEDIATE")
            try:
                limit,spent=db.execute("SELECT limit_units,spent FROM evolution_budget WHERE id=1").fetchone()
                if spent+reserve>limit:db.rollback();return {"status":"PAUSED_BUDGET_EXHAUSTED","can_promote":False}
                cycle=db.execute("SELECT coalesce(max(id),0)+1 FROM evolution_cycles").fetchone()[0]
                body={"contract_sha256":self.contract_sha,"sources":sources,"reserved_work":reserve,
                      "engine_pin":engine_pin(),"started_at":self.clock(),
                      "max_candidates":self.config["max_candidates"],"champion":None if not champion else {"branch":champion[0],"program":json.loads(champion[1])}}
                db.execute("UPDATE evolution_budget SET spent=spent+? WHERE id=1",(reserve,))
                if family is not None:db.execute("INSERT INTO evolution_families VALUES(?,?)",(family,cycle))
                for row in sources:
                    if row["split"]=="EVALUATION":db.execute("INSERT INTO evolution_used_sources VALUES(?,?)",(row["source_sha256"],cycle))
                db.execute("INSERT INTO evolution_cycles VALUES(?,?,?,?)",(cycle,self.contract_sha,"PLANNED",canonical(body).decode()));db.commit()
            except Exception:db.rollback();raise
            stage="PLANNED"
        root="evo-root-"+self.contract_sha[:16]
        if root not in self.garden.replay()["branches"]:
            self._event(cycle,"root","PROPOSE",root,"Purpose-scoped baseline; grammar and activation must evolve without losing required source distinctions.")
        if stage=="PLANNED":
            state=self.garden.replay();history=[]
            for _,old in db.execute("SELECT id,body FROM evolution_cycles WHERE stage='DONE' ORDER BY id DESC LIMIT 4"):
                previous=json.loads(old)
                findings=[]
                for finding in previous.get("development_findings",[])[:2]:
                    diagnostics=[{k:d[k] for k in ("id","candidate_bytes","baseline_bytes")} for d in finding["diagnostics"][:4]]
                    old_program=finding["program"]
                    if old_program is not None and len(canonical(old_program))>2048:
                        old_program={"program_sha256":fingerprint(old_program),"details":"Retained in branch receipt; omitted from planning preview budget"}
                    findings.append({"branch":finding["branch"],"hypothesis":finding["hypothesis"][:512],"program":old_program,"failure":finding["failure"],"diagnostics":diagnostics})
                history.append({"cycle":previous["result"]["cycle"],"development_findings":findings,
                                "research_champion":previous["result"].get("research_champion")})
            training=[];preview_budget=8192
            for r in body["sources"]:
                if r["split"]!="TRAIN" or preview_budget==0:continue
                raw=self.store.get(r["source_sha256"]);sample=raw[:min(2048,preview_budget)];preview_budget-=len(sample)
                training.append({"id":r["id"],"sample_base64":base64.b64encode(sample).decode(),"preview_only":len(sample)<len(raw)})
            context={"packspec":self.config["packspec"],"training_samples":training,"history":history,
                     "branches":[{"id":k,"active":v["active"],"parents":v["parents"]} for k,v in list(state["branches"].items())[-64:]],
                     "champion":body["champion"],"max_candidates":body["max_candidates"],
                     "evaluation_data":"SEALED_FRESH_FAMILIES_NOT_DISCLOSED" if any(r["split"]=="EVALUATION" for r in body["sources"]) else "UNAVAILABLE_DEVELOPMENT_ONLY"}
            # A crash after reservation cannot obtain repeated free model calls.
            self._save(cycle,"REQUESTED",body)
            try:
                response=proposer.propose(context)
                if not isinstance(response,dict) or not isinstance(response.get("candidates"),list) or not 1<=len(response["candidates"])<=body["max_candidates"]:
                    raise ValueError("Bounded candidates required")
                body["response"]=response;self._save(cycle,"PROPOSED",body)
            except Exception as exc:
                body["provider_failure"]=type(exc).__name__;self._save(cycle,"REQUESTED",body)
                return {"status":"PROVIDER_FAILED_REQUIRES_EXPLICIT_RETRY","cycle":cycle,"can_promote":False}
        elif stage=="REQUESTED":
            return {"status":"PROVIDER_FAILED_REQUIRES_EXPLICIT_RETRY","cycle":cycle,"can_promote":False}
        if "response" not in body:raise ValueError("Missing durable proposal snapshot")
        state=self.garden.replay();outcomes=list(body.get("outcomes",[]));development=list(body.get("development_findings",[]));best=None
        for outcome in outcomes:
            if outcome["status"]=="IMPROVED_ON_FRESH_COHORT":
                score=(outcome["evaluation_bytes"],len(canonical(outcome["program"])))
                if best is None or score<best[0]:best=(score,outcome)
        for number,candidate in enumerate(body["response"]["candidates"]):
            if number<len(outcomes):continue
            branch=f"evo-{cycle}-candidate-{number}"
            hypothesis=candidate.get("hypothesis","Invalid proposal") if isinstance(candidate,dict) else "Invalid proposal"
            parents=candidate.get("parents",[]) if isinstance(candidate,dict) else []
            invalid_lineage=(not isinstance(parents,list) or len(parents)>2 or any(not isinstance(p,str) for p in parents)
                    or len(set(parents))!=len(parents) or any(p not in state["branches"] for p in parents))
            if invalid_lineage:parents=[]
            if not parents:parents=[body["champion"]["branch"] if body["champion"] else root]
            # Revisit prior failed branches without erasing their counterexamples.
            for parent in parents:
                if not state["branches"][parent]["active"]:
                    self._event(cycle,f"reopen-{parent}","REOPEN",parent,"A new grammar/activation investigation revisits this branch; previous negative evidence is retained.")
            statement=str(hypothesis).strip() or "Invalid empty hypothesis"
            self._event(cycle,f"propose-{number}","SYNTHESIZE" if len(parents)>1 else "PROPOSE",branch,statement,parents=parents)
            cached=db.execute("SELECT uri FROM research_evidence WHERE evidence_id=?",(f"evo-{cycle}-test-{number}",)).fetchone()
            if cached:
                outcome=strict_json(self.store.get(cached[0].removeprefix("sha256://")))
                if outcome["branch"]!=branch:raise ValueError("Recovered receipt belongs to another branch")
                rows=outcome["measurements"]
            else:
                rows=[]
                try:
                    if body.get("attempting")==number:
                        raise ValueError("Interrupted experiment is not silently repeated under the original work reservation")
                    body["attempting"]=number;self._save(cycle,"EVALUATING",body)
                    if invalid_lineage or not isinstance(hypothesis,str) or not 1<=len(hypothesis.strip())<=2000:raise ValueError("Typed hypothesis and existing unique parents required")
                    if set(candidate)!={"hypothesis","parents","program"}:raise ValueError("Unsupported proposal fields")
                    validate(candidate["program"])
                    training=[self.store.get(r["source_sha256"]) for r in body["sources"] if r["split"]=="TRAIN"]
                    for rule in candidate["program"]["rules"]:
                        if rule["op"]=="productions":
                            for production in rule["rules"]:
                                if not any(production["literal"].encode() in raw for raw in training):raise ValueError("Production lacks a training source anchor")
                    for source in body["sources"]:
                        raw=self.store.get(source["source_sha256"])
                        current,payload=experiment(raw,candidate["program"],decoder_install_bytes=self.config["packspec"]["decoder_install_bytes"])
                        current["packspec_sha256"]=self.contract_sha
                        current["artifact_sha256"]=self.store.put(payload)
                        current_sha=self.store.put(canonical(current))
                        reference=None
                        reference_sha=None
                        if body["champion"]:
                            begin=time.perf_counter_ns()
                            try:reference,_=experiment(raw,body["champion"]["program"],decoder_install_bytes=self.config["packspec"]["decoder_install_bytes"])
                            except Exception as exc:
                                reference={"baseline_bytes":len(raw),"candidate_bytes":None,"selected_bytes":len(raw),
                                    "fallback":True,"experiment_wall_ns":time.perf_counter_ns()-begin,
                                    "activation":{"activation_ns":None,"steps":0,"modules":[],"activated_chunks":[],"productions_materialized":[]},
                                    "refusal":type(exc).__name__,"baseline_decoder_cost":"UNMEASURED"}
                            reference["packspec_sha256"]=self.contract_sha
                            reference_sha=self.store.put(canonical(reference))
                        def summarized(receipt):
                            return {key:receipt[key] for key in ("baseline_bytes","candidate_bytes","selected_bytes","fallback","experiment_wall_ns")} | {
                                "activation":{key:receipt["activation"][key] for key in ("activation_ns","steps","modules")} | {
                                    "activated_chunks":len(receipt["activation"]["activated_chunks"]),
                                    "productions_materialized":len(receipt["activation"]["productions_materialized"])}}
                        rows.append({"id":source["id"],"family":source["family"],"split":source["split"],
                                     "candidate":summarized(current),"receipt_sha256":current_sha,
                                     "champion_receipt_sha256":reference_sha,
                                     "champion":None if reference is None else summarized(reference)})
                    evaluations=[r for r in rows if r["split"]=="EVALUATION"]
                    comparisons=evaluations or [r for r in rows if r["split"]=="DEV"]
                    candidate_bytes=sum(r["candidate"]["selected_bytes"] for r in comparisons)
                    champion_bytes=sum((r["champion"] or r["candidate"])["selected_bytes"] if r["champion"] else r["candidate"]["baseline_bytes"] for r in comparisons)
                    # Select only within the same purpose, fresh cohort and full delivered-byte cost.
                    score=(candidate_bytes,len(canonical(candidate["program"])))
                    qualified=bool(evaluations) and candidate_bytes<champion_bytes
                    status="IMPROVED_ON_FRESH_COHORT" if qualified else ("DEV_PROMISING_EVALUATION_REQUIRED" if not evaluations and candidate_bytes<champion_bytes else "NO_IMPROVEMENT")
                    outcome={"branch":branch,"program":candidate["program"],"status":status,
                             "packspec_sha256":self.contract_sha,"source_manifest_sha256":fingerprint(body["sources"]),
                             "evaluation_bytes":candidate_bytes,"champion_bytes":champion_bytes,"measurements":rows,
                             "promotion_scope":"RESEARCH_BYTES_CHAMPION_ONLY","total_cost_advantage":"NOT_ESTABLISHED"}
                except Exception as exc:
                    outcome={"branch":branch,"status":"REFUSED","failure":type(exc).__name__,
                             "packspec_sha256":self.contract_sha,"source_manifest_sha256":fingerprint(body["sources"]),
                             "failure_reason":str(exc)[:400],"measurements":rows}
            if outcome["status"]=="IMPROVED_ON_FRESH_COHORT":
                score=(outcome["evaluation_bytes"],len(canonical(outcome["program"])))
                if best is None or score<best[0]:best=(score,outcome)
            # Future agents receive development diagnostics, never held-out cases or measurements.
            diagnostics=[{"id":r["id"],"candidate_bytes":r["candidate"]["candidate_bytes"],
                          "baseline_bytes":r["candidate"]["baseline_bytes"],"activation":r["candidate"]["activation"]}
                         for r in rows if r["split"]!="EVALUATION"]
            development.append({"branch":branch,"hypothesis":str(hypothesis),"program":candidate.get("program") if isinstance(candidate,dict) else None,
                                "diagnostics":diagnostics,"failure":outcome.get("failure_reason",outcome.get("failure"))})
            eid,address=self._receipt(cycle,f"test-{number}",outcome)
            self._event(cycle,f"test-{number}","TEST",branch,"Observed experiment receipt sha256:"+address,evidence_ids=[eid])
            if outcome["status"]!="IMPROVED_ON_FRESH_COHORT":
                self._event(cycle,f"challenge-{number}","CHALLENGE",branch,"Counterexample: "+outcome["status"]+". Evidence and activation trace retained at sha256:"+address)
                if outcome["status"]!="DEV_PROMISING_EVALUATION_REQUIRED":self._event(cycle,f"prune-{number}","PRUNE",branch,"Dormant under this purpose/cohort; retained for later reopening.")
            outcomes.append(outcome)
            body.pop("attempting",None)
            body["outcomes"]=outcomes;body["development_findings"]=development
            self._save(cycle,"EVALUATING",body)
        fresh=sorted({r["family"] for r in body["sources"] if r["split"]=="EVALUATION"})
        result={"schema":"qualityrag.evolution-cycle/v1","status":"COMPLETE" if fresh else "DEVELOPMENT_ONLY","cycle":cycle,
                "engine_pin":body["engine_pin"],"packspec_sha256":self.contract_sha,
                "research_champion":best[1]["branch"] if best else (body["champion"]["branch"] if body["champion"] else None),
                "promoted_this_cycle":best is not None,"outcomes":outcomes,
                "fresh_evaluation_families":fresh,
                "provider":body["response"].get("provider",{}),"work_reserved":body["reserved_work"],
                "qualityrag_admission":"INCONCLUSIVE","can_generate":False,"can_release":False,
                "scientific_generalization":"NOT_ESTABLISHED","total_cost_advantage":"NOT_ESTABLISHED"}
        body["development_findings"]=development;body["result"]=result
        body.pop("outcomes",None)
        db.execute("BEGIN IMMEDIATE")
        try:
            if best:
                db.execute("INSERT INTO evolution_champions VALUES(?,?,?) ON CONFLICT(contract_sha) DO UPDATE SET branch=excluded.branch,program=excluded.program",
                    (self.contract_sha,best[1]["branch"],canonical(best[1]["program"]).decode()))
            db.execute("UPDATE evolution_cycles SET stage='DONE',body=? WHERE id=?",(canonical(body).decode(),cycle));db.commit()
        except Exception:db.rollback();raise
        return result


def main(argv=None):
    p=argparse.ArgumentParser(description="Grow the persistent RCT research Garden")
    p.add_argument("--garden",required=True);p.add_argument("--config")
    p.add_argument("--status",action="store_true")
    p.add_argument("--model");p.add_argument("--ollama-endpoint",default="http://127.0.0.1:11434/api/chat")
    p.add_argument("--work-limit",type=int,default=200);p.add_argument("--continuous",action="store_true")
    p.add_argument("--public-contract-root",help="optional existing service object-store root; publishes only the purpose contract")
    p.add_argument("--tenant",default="research")
    p.add_argument("--retry-provider",action="store_true",help="charge an explicit retry of an interrupted provider request")
    p.add_argument("--interval",type=float,default=10)
    args=p.parse_args(argv)
    if args.status:
        print(json.dumps(status(args.garden),sort_keys=True));return
    if not args.config or not args.model:p.error("--config and --model are required to grow the Garden")
    if not 1<=args.interval<=3600:raise ValueError("Bounded scheduling interval")
    retry=args.retry_provider
    while True:
        public=ArtifactStore(args.public_contract_root,tenant=args.tenant) if args.public_contract_root else None
        garden=EvolutionGarden(args.garden,strict_json(Path(args.config).read_bytes()),work_limit=args.work_limit,public_contract_store=public)
        try:
            if retry:garden.retry_provider();retry=False
            result=garden.cycle(OllamaProposer(args.model,args.ollama_endpoint));print(json.dumps(result,sort_keys=True),flush=True)
        finally:garden.close()
        if not args.continuous or result["status"] not in {"COMPLETE","DEVELOPMENT_ONLY"}:break
        time.sleep(args.interval)


if __name__=="__main__":main()
