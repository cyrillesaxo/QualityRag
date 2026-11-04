"""Pre-registration, family-disjoint datasets, paired statistics and codec ablations."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import random
import sqlite3
from statistics import mean
from time import perf_counter_ns

from .common import canonical,fingerprint,identity,HEX,strict_json
from .scene_codec import train_model,encode,decode_frames,frames,canon
from .media import benchmark_av1


class Registry:
    def __init__(self,path,*,registry_id,tenant,reviewer_keys,reviewer_subjects,author_public_key,clock=None):
        from datetime import datetime,timezone
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        identity(registry_id);identity(tenant)
        if not isinstance(reviewer_keys,dict) or len(reviewer_keys)>32 or not isinstance(author_public_key,Ed25519PublicKey):
            raise ValueError("Host-configured holdout authority required")
        if not isinstance(reviewer_subjects,dict) or set(reviewer_subjects)!=set(reviewer_keys):
            raise ValueError("Every evaluator key must have a host-assigned subject")
        for key_id,key in reviewer_keys.items():
            identity(key_id)
            identity(reviewer_subjects[key_id])
            if not isinstance(key,Ed25519PublicKey):raise ValueError("Invalid evaluator public key")
        self.registry_id=registry_id;self.tenant=tenant
        self.reviewer_keys=dict(reviewer_keys);self.author_public_key=author_public_key
        self.reviewer_subjects=dict(reviewer_subjects)
        self.clock=clock or (lambda:datetime.now(timezone.utc).isoformat())
        self.db=sqlite3.connect(path,timeout=5)
        if not next(row[2] for row in self.db.execute("PRAGMA database_list") if row[1]=="main"):
            self.db.close();raise ValueError("Durable experiment registry required")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS experiment_protocols(id TEXT PRIMARY KEY,body TEXT NOT NULL,sha TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS experiment_opens(id TEXT PRIMARY KEY,protocol_sha TEXT NOT NULL,actor TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS experiment_registrations(
          id TEXT PRIMARY KEY REFERENCES experiment_protocols(id),body TEXT NOT NULL,sha TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS experiment_holdout_receipts(
          id TEXT PRIMARY KEY REFERENCES experiment_opens(id) DEFERRABLE INITIALLY DEFERRED,
          tenant TEXT NOT NULL,nonce TEXT NOT NULL,body TEXT NOT NULL,sha TEXT NOT NULL,
          UNIQUE(tenant,nonce));
        """)
        for table in ("experiment_protocols","experiment_opens","experiment_registrations","experiment_holdout_receipts"):
            for action in ("UPDATE","DELETE"):
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable'); END")
    def close(self):self.db.close()

    def _atomic(self):
        from contextlib import contextmanager
        @contextmanager
        def transaction():
            nested=self.db.in_transaction
            self.db.execute("SAVEPOINT experiment_write" if nested else "BEGIN IMMEDIATE")
            try:
                yield
                if nested:self.db.execute("RELEASE experiment_write")
                else:self.db.commit()
            except Exception:
                if nested:
                    self.db.execute("ROLLBACK TO experiment_write");self.db.execute("RELEASE experiment_write")
                else:self.db.rollback()
                raise
        return transaction()

    @staticmethod
    def _instant(value):
        from datetime import datetime
        if not isinstance(value,str):raise ValueError("Timezone-aware registration time required")
        instant=datetime.fromisoformat(value.replace("Z","+00:00"))
        if instant.utcoffset() is None:raise ValueError("Timezone-aware registration time required")
        return instant

    def register(self,protocol):
        if not isinstance(protocol,dict) or set(protocol)!={"id","hypotheses","arms","metrics","rejection","sample_plan","dataset_sha256","registered_at"}:
            raise ValueError("Complete preregistration required")
        identity(protocol["id"])
        if not isinstance(protocol["hypotheses"],dict) or set(protocol["hypotheses"])!={"H1","H2","H3","H4","H5","H6"}:
            raise ValueError("All six hypotheses need independent/dependent variables")
        for item in protocol["hypotheses"].values():
            if not isinstance(item,dict) or set(item)!={"independent","dependent","null"} or any(not isinstance(item[k],str) or not 1<=len(item[k].strip())<=2000 for k in item):raise ValueError("Explicit falsifiable hypothesis required")
        if not isinstance(protocol["arms"],list) or len(protocol["arms"])!=6 or any(not isinstance(arm,str) for arm in protocol["arms"]) or set(protocol["arms"])!={"av1","neural","no-grammar","fixed","decoder-only","paired"}:
            raise ValueError("All comparators must be preregistered")
        if (any(not isinstance(protocol[k],dict) or not protocol[k] for k in ("sample_plan","rejection","metrics"))
                or not isinstance(protocol["dataset_sha256"],str) or not HEX.fullmatch(protocol["dataset_sha256"])):
            raise ValueError("Sample rationale, metrics, thresholds and pinned corpus required")
        sha=fingerprint(protocol)
        observed_at=self.clock()
        if self._instant(protocol["registered_at"])>self._instant(observed_at):raise ValueError("Registration cannot be in the future")
        record={"schema":"qualityrag.experiment-registration/v1","registry_id":self.registry_id,
                "tenant":self.tenant,"protocol_sha256":sha,"observed_at":observed_at}
        with self._atomic():
            self.db.execute("INSERT INTO experiment_protocols VALUES(?,?,?)",(protocol["id"],canonical(protocol).decode(),sha))
            self.db.execute("INSERT INTO experiment_registrations VALUES(?,?,?)",(protocol["id"],canonical(record).decode(),fingerprint(record)))
        return sha

    def _protocol(self,protocol_id):
        identity(protocol_id)
        row=self.db.execute("SELECT body,sha FROM experiment_protocols WHERE id=?",(protocol_id,)).fetchone()
        registration=self.db.execute("SELECT body,sha FROM experiment_registrations WHERE id=?",(protocol_id,)).fetchone()
        if not row or not registration:raise ValueError("Unregistered protocol or legacy record without observed registration")
        protocol=strict_json(row[0].encode());record=strict_json(registration[0].encode())
        if (protocol.get("id")!=protocol_id or fingerprint(protocol)!=row[1] or fingerprint(record)!=registration[1]
                or record.get("protocol_sha256")!=row[1] or record.get("registry_id")!=self.registry_id or record.get("tenant")!=self.tenant):
            raise ValueError("Protocol or registration integrity mismatch")
        return protocol,record,registration[1]

    def holdout_context(self,protocol_id,*,actor,dataset_sha256):
        identity(actor)
        protocol,record,registration_sha=self._protocol(protocol_id)
        if protocol["dataset_sha256"]!=dataset_sha256:raise ValueError("Unregistered or changed dataset")
        return {"schema":"qualityrag.holdout-access/v1","purpose":"OPEN_REGISTERED_HOLDOUT",
                "registry_id":self.registry_id,"tenant":self.tenant,"actor":actor,"protocol_id":protocol_id,
                "protocol_sha256":record["protocol_sha256"],"registration_sha256":registration_sha,
                "dataset_sha256":dataset_sha256}

    def open_holdout(self,protocol_id,*,actor,dataset_sha256,signed_review):
        from .authority import check_review
        with self._atomic():
            context=self.holdout_context(protocol_id,actor=actor,dataset_sha256=dataset_sha256)
            protocol,registration,_=self._protocol(protocol_id)
            opened_at=self.clock()
            if self._instant(opened_at)<self._instant(registration["observed_at"]):raise ValueError("Opening predates observed registration")
            checked=check_review(signed_review,self.reviewer_keys,context=context,
                author_public_key=self.author_public_key,as_of=opened_at)
            if checked["reviewer"]!=actor or self.reviewer_subjects[checked["review_key_id"]]!=actor:
                raise PermissionError("Holdout actor must match the host-assigned signer")
            body={"schema":"qualityrag.holdout-opening/v1","context":context,"opened_at":opened_at,
                  "reviewer_key_id":checked["review_key_id"],"review_envelope":signed_review,
                  "boundary":"Host-authorized protocol opening, not proof of scientific independence or corpus access"}
            try:
                self.db.execute("INSERT INTO experiment_holdout_receipts VALUES(?,?,?,?,?)",
                    (protocol_id,self.tenant,checked["nonce"],canonical(body).decode(),fingerprint(body)))
            except sqlite3.IntegrityError as exc:raise PermissionError("Holdout opening or nonce already recorded") from exc
            self.db.execute("INSERT INTO experiment_opens VALUES(?,?,?)",(protocol_id,context["protocol_sha256"],actor))
        return protocol

    def opening_receipt(self,protocol_id):
        identity(protocol_id)
        row=self.db.execute("SELECT body,sha FROM experiment_holdout_receipts WHERE id=?",(protocol_id,)).fetchone()
        if not row:raise ValueError("No authenticated holdout opening")
        receipt=strict_json(row[0].encode())
        if fingerprint(receipt)!=row[1]:raise ValueError("Holdout receipt integrity mismatch")
        return receipt


def dataset_manifest(records,*,minimum_clips=100):
    if type(minimum_clips) is not int or minimum_clips<1 or not isinstance(records,list) or len(records)<minimum_clips:
        raise ValueError("Representative licensed corpus size not met")
    identities=set();families={};checked=[]
    for row in records:
        if set(row)!={"id","path","family","split","rights_ref","redistributable","annotations"}:
            raise ValueError("Dataset rights/provenance/annotations required")
        identity(row["id"]);identity(row["family"])
        if row["split"] not in {"train","dev","holdout"} or type(row["redistributable"]) is not bool or not row["rights_ref"]:
            raise ValueError("Explicit licensed split required")
        if not isinstance(row["annotations"],dict) or set(row["annotations"])!={"audio","on_screen_text","timing","scene_dynamics"}:
            raise ValueError("Ground-truth annotation inventory required")
        path=Path(row["path"]).resolve();digest=sha256(path.read_bytes()).hexdigest()
        if digest in identities:raise ValueError("Duplicated source content leaks across corpus")
        identities.add(digest)
        if row["family"] in families and families[row["family"]]!=row["split"]:
            raise ValueError("Scene family leakage")
        families[row["family"]]=row["split"]
        checked.append({**row,"path":str(path),"source_sha256":digest})
    if set(r["split"] for r in records)!={"train","dev","holdout"}:raise ValueError("Train/dev/holdout all required")
    return {"schema":"qualityrag.media-dataset/v1","records":checked,"sha256":fingerprint(checked),
            "rights_assurance":"CALLER_DOCUMENTED_REQUIRES_INDEPENDENT_REVIEW"}


def paired_interval(before,after,*,seed=1701,resamples=2000):
    if not isinstance(before,(list,tuple)) or not isinstance(after,(list,tuple)) or len(before)!=len(after) or not 2<=len(before)<=10000:raise ValueError("Paired independent-family samples required")
    if type(seed) is not int or not 0<=seed<=2**63-1 or type(resamples) is not int or not 100<=resamples<=10000:
        raise ValueError("Bounded integer seed and 100-10000 resamples required")
    if len(before)*resamples>20_000_000:raise ValueError("Bootstrap draw budget exceeded")
    import math
    try:finite=all(type(v) in (int,float) and math.isfinite(v) for v in list(before)+list(after))
    except OverflowError:finite=False
    if not finite:
        raise ValueError("Finite measurements required")
    deltas=[a-b for b,a in zip(before,after)]
    if any(not math.isfinite(value) for value in deltas):raise ValueError("Paired deltas exceed finite range")
    rng=random.Random(seed)
    means=sorted(mean(rng.choices(deltas,k=len(deltas))) for _ in range(resamples))
    return {"paired_mean_delta":mean(deltas),"ci95":[means[int(.025*resamples)],means[int(.975*resamples)]],
            "method":"PAIRED_PERCENTILE_BOOTSTRAP","seed":seed,"resamples":resamples,
            "sample_unit":"INDEPENDENT_FAMILY","independence":"CALLER_DECLARED_NOT_VERIFIED",
            "scope":"SUPPLIED_SAMPLES_ONLY","draws":len(before)*resamples}


def run_codec_arms(training,heldout,output):
    """Fixed pair, fixed encoder/decoder optimization, paired palette search.

    The paired palette is selected on training bytes only. The hidden clips are
    used once for evaluation. All search encoding work is included explicitly.
    """
    train_ids={sha256(Path(p).read_bytes()).hexdigest() for p in training}
    held_ids={sha256(Path(p).read_bytes()).hexdigest() for p in heldout}
    if not train_ids or not held_ids or train_ids&held_ids:raise ValueError("Disjoint actual train/heldout sources required")
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    start=perf_counter_ns();base=train_model(training)
    from .agents import propose
    model_proposal=propose("grammar-compiler",parent_grammar=base,task={"candidate_model_sizes":[1,4,8,16]})
    decoder_proposal=propose("activation-optimizer",parent_grammar=base,task={"decoder_variants":["scalar","strided"]})
    if model_proposal["status"]!="PROPOSAL" or decoder_proposal["status"]!="PROPOSAL":
        raise ValueError("Isolated candidate generation unavailable")
    sizes=[p["value"] for p in model_proposal["proposal"]["artifact"]["model_patches"]]
    variants=decoder_proposal["proposal"]["artifact"]["decoder_candidates"]
    candidates=[];decoder_times={variant:0 for variant in variants}
    for size in sizes:
        model={**deepcopy(base),"palette":base["palette"][:size]}
        score=0
        for source in training:
            payload,_=encode(source,model);score+=len(canon(payload))
            for variant in variants:
                begin=perf_counter_ns();decode_frames(payload,model,implementation=variant)
                decoder_times[variant]+=perf_counter_ns()-begin
        candidates.append((score+len(canon(model)),size,model))
    optimized=min(candidates,key=lambda x:(x[0],x[1]))[2]
    decoder=min(decoder_times,key=lambda key:(decoder_times[key],key))
    search_ns=perf_counter_ns()-start
    results=[]
    for index,source in enumerate(heldout):
        original=frames(source)["frames"]
        fixed,_=encode(source,base)
        for arm,model,payload,variant in (("fixed",base,fixed,"scalar"),("decoder-only",base,fixed,decoder),
                                  ("paired",optimized,None,decoder)):
            start=perf_counter_ns()
            if payload is None:payload,encoding=encode(source,model)
            else:encoding={"encode_ns":None,"reused_fixed_encoder":True}
            reconstructed=decode_frames(payload,model,implementation=variant)
            elapsed=perf_counter_ns()-start
            row={"case":index,"arm":arm,"source_sha256":sha256(Path(source).read_bytes()).hexdigest(),
                 "model_sha256":__import__("tools.activation_runtime.scene_codec",fromlist=["digest"]).digest(model),
                 "payload_bytes":len(canon(payload)),"model_bytes":len(canon(model)),
                 "evaluation_ns":elapsed,"encoding":encoding,"exact_frame_match":reconstructed==original,
                 "search_ns":search_ns if arm in {"paired","decoder-only"} else 0,
                 "decoder_variant":variant,"decoder_only_boundary":"Fixed encoder/model; decoder selected using training data only" if arm=="decoder-only" else None}
            results.append(row)
        baseline=benchmark_av1(source,out/("av1-"+str(index)+".mkv"),rights_ref="host-dataset-rights-reference-required",split_family="host-family-manifest-required")
        baseline["rgb_frame_match"]=frames(out/("av1-"+str(index)+".mkv"))["frames"]==original
        results.append({"case":index,"arm":"av1",**baseline})
    receipt={"schema":"qualityrag.codec-ablation/v1","measurements":results,
             "training_search_ns":search_ns,"training_decoder_times_ns":decoder_times,"candidate_proposals":{"model":model_proposal,"decoder":decoder_proposal},"training_sources":sorted(train_ids),"heldout_sources":sorted(held_ids),
             "neural_comparator":"UNAVAILABLE_UNTIL_PINNED_LICENSED_WEIGHTS_PROVIDED",
             "no_grammar_comparator":"RAW_RGB_SOURCE_BYTES","total_cost_advantage":"NOT_ESTABLISHED",
             "independent_fidelity_review":"PENDING","can_generate":False}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True))
    return receipt
