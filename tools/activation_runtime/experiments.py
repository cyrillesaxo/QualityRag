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

from .common import canonical,fingerprint,identity
from .scene_codec import train_model,encode,decode_frames,frames,canon
from .media import benchmark_av1


class Registry:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS experiment_protocols(id TEXT PRIMARY KEY,body TEXT NOT NULL,sha TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS experiment_opens(id TEXT PRIMARY KEY,protocol_sha TEXT NOT NULL,actor TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS protocol_no_update BEFORE UPDATE ON experiment_protocols BEGIN SELECT RAISE(ABORT,'immutable'); END;
        CREATE TRIGGER IF NOT EXISTS protocol_no_delete BEFORE DELETE ON experiment_protocols BEGIN SELECT RAISE(ABORT,'immutable'); END;
        """)
    def close(self):self.db.close()

    def register(self,protocol):
        if not isinstance(protocol,dict) or set(protocol)!={"id","hypotheses","arms","metrics","rejection","sample_plan","dataset_sha256","registered_at"}:
            raise ValueError("Complete preregistration required")
        identity(protocol["id"])
        if set(protocol["hypotheses"])!={"H1","H2","H3","H4","H5","H6"}:
            raise ValueError("All six hypotheses need independent/dependent variables")
        for item in protocol["hypotheses"].values():
            if set(item)!={"independent","dependent","null"} or any(not item[k] for k in item):raise ValueError("Explicit falsifiable hypothesis required")
        if set(protocol["arms"])!={"av1","neural","no-grammar","fixed","decoder-only","paired"}:
            raise ValueError("All comparators must be preregistered")
        if (not protocol["sample_plan"] or not protocol["rejection"] or not protocol["metrics"]
                or len(protocol["dataset_sha256"])!=64):
            raise ValueError("Sample rationale, metrics, thresholds and pinned corpus required")
        sha=fingerprint(protocol)
        with self.db:self.db.execute("INSERT INTO experiment_protocols VALUES(?,?,?)",
                                   (protocol["id"],canonical(protocol).decode(),sha))
        return sha

    def open_holdout(self,protocol_id,*,actor,role,dataset_sha256):
        identity(actor)
        if role!="independent-evaluator":raise PermissionError("Proposers may not open holdout")
        row=self.db.execute("SELECT body,sha FROM experiment_protocols WHERE id=?",(protocol_id,)).fetchone()
        if not row or json.loads(row[0])["dataset_sha256"]!=dataset_sha256:raise ValueError("Unregistered or changed dataset")
        with self.db:self.db.execute("INSERT INTO experiment_opens VALUES(?,?,?)",(protocol_id,row[1],actor))
        return json.loads(row[0])


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
    if len(before)!=len(after) or not 2<=len(before)<=10000:raise ValueError("Paired independent-family samples required")
    import math
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in list(before)+list(after)):
        raise ValueError("Finite measurements required")
    deltas=[a-b for b,a in zip(before,after)]
    rng=random.Random(seed)
    means=sorted(mean(rng.choices(deltas,k=len(deltas))) for _ in range(resamples))
    return {"paired_mean_delta":mean(deltas),"ci95":[means[int(.025*resamples)],means[int(.975*resamples)]],
            "method":"PAIRED_PERCENTILE_BOOTSTRAP","seed":seed,"resamples":resamples,
            "sample_unit":"INDEPENDENT_FAMILY","scope":"SUPPLIED_SAMPLES_ONLY"}


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
