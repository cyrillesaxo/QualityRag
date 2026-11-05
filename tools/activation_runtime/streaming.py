"""Content-addressed independent frame segments, verified release and range seeking."""
from copy import deepcopy
from hashlib import sha256
import json
from fractions import Fraction
from time import perf_counter_ns
from .scene_codec import canon,digest,decode_frames,_model,MAX_FRAMES,MAX_RAW,PAYLOAD_SCHEMA
from .common import identity,HEX,strict_json
from .artifacts import ArtifactStore
from signed_bundles import sign,verify,ATTEST_SCHEMA,_validate_period


def _index(index):
    """Validate the signed index before allocating placeholders or fetching frames."""
    if (not isinstance(index,dict) or set(index)!={"schema","header","model_object","segments","variants"}
        or index["schema"]!="qualityrag.scene-segment-index/v1" or index["variants"]!=["reference","raw"]):
        raise ValueError("Unsupported segment index")
    header=index["header"]
    if (not isinstance(header,dict) or "frames" in header or header.get("schema")!=PAYLOAD_SCHEMA or
        header.get("codec")!="scene-palette-rgb/v1" or header.get("runtime_abi")!="python-scene-reference/v1" or
        header.get("normalized_profile")!="RGB24_CFR_AND_PCM32_AUDIO"):
        raise ValueError("Unsupported streaming header")
    for address in (index["model_object"],header.get("model_sha256"),header.get("source_sha256")):
        if not isinstance(address,str) or not HEX.fullmatch(address):raise ValueError("Pinned streaming hashes required")
    if index["model_object"]!=header["model_sha256"]:raise ValueError("Index/model mismatch")
    count=header.get("frame_count");width=header.get("width");height=header.get("height")
    if (any(type(n) is not int for n in (count,width,height)) or not 1<=count<=MAX_FRAMES or
        not 1<=width<=512 or not 1<=height<=512 or count*width*height*3>MAX_RAW):
        raise ValueError("Streaming memory/frame budget")
    def rational(value):
        if not isinstance(value,str) or not 1<=len(value)<=64:raise ValueError("Bounded timestamp string required")
        try:return Fraction(value)
        except (ValueError,ZeroDivisionError) as exc:raise ValueError("Invalid streaming time") from exc
    fps=rational(header.get("fps"))
    if not 0<fps<=30 or count/fps>10:raise ValueError("Streaming rate/duration budget")
    times=header.get("source_frame_pts")
    if not isinstance(times,list) or len(times)!=count:raise ValueError("Missing streaming timestamps")
    pts=[rational(value) for value in times]
    if any(value<0 or abs(value-Fraction(i)/fps)>Fraction(1,1000) or (i>0 and value<=pts[i-1])
           for i,value in enumerate(pts)):
        raise ValueError("Unsupported streaming timeline")
    rows=index["segments"]
    if not isinstance(rows,list) or len(rows)!=count:raise ValueError("Missing streaming segments")
    for i,row in enumerate(rows):
        if (not isinstance(row,dict) or set(row)!={"index","variants","dependencies","frame_sha256"} or
            type(row["index"]) is not int or row["index"]!=i or row["dependencies"]!=[index["model_object"]] or
            not isinstance(row["variants"],dict) or set(row["variants"])!={"reference","raw"}):
            raise ValueError("Streaming dependency, variant or ordering mismatch")
        for address in [row["frame_sha256"],*row["variants"].values()]:
            if not isinstance(address,str) or not HEX.fullmatch(address):raise ValueError("Pinned segment hashes required")
    return index


def package(payload,model,store):
    if not isinstance(store,ArtifactStore) or payload["model_sha256"]!=digest(model):
        raise ValueError("Typed store and compatible model required")
    # Verify the full candidate once before publishing an index.
    exact=decode_frames(payload,model)
    model_sha=store.put(canon(model))
    header={k:v for k,v in payload.items() if k!="frames"}
    rows=[]
    import base64
    for original,raw in zip(payload["frames"],exact):
        reference=store.put(canon(original))
        uncompressed={**original,"mode":"raw","data":base64.b64encode(raw).decode()}
        rows.append({"index":original["index"],"variants":{"reference":reference,"raw":store.put(canon(uncompressed))},
                     "dependencies":[model_sha],"frame_sha256":original["frame_sha256"]})
    index={"schema":"qualityrag.scene-segment-index/v1","header":header,"model_object":model_sha,
           "segments":rows,"variants":["reference","raw"]}
    _index(index)
    return store.put(canon(index)),index


# The codec grammar is pinned separately from the shared model: it names the payload schema,
# codec and reconstruction algorithm a decoder must implement.
SCENE_GRAMMAR={"schema":"qualityrag.scene-grammar/v1","payload_schema":PAYLOAD_SCHEMA,
               "codec":"scene-palette-rgb/v1","algorithm":"flat-backdrop-rgb-xor/v1"}


def release(index_sha,index,*,tenant,policy_ir_sha256,run_id,sequence):
    identity(tenant);identity(run_id)
    _index(index)
    if digest(index)!=index_sha:raise ValueError("Release index hash mismatch")
    if type(sequence) is not int or not 1<=sequence<=1_000_000_000:raise ValueError("Release sequence")
    if any(not isinstance(h,str) or not HEX.fullmatch(h) for h in (index_sha,policy_ir_sha256,index["model_object"],index["header"]["source_sha256"])):
        raise ValueError("Pinned release hashes required")
    decoder=sha256(__import__("pathlib").Path(__file__).with_name("scene_codec.py").read_bytes()).hexdigest()
    return {"schema":"qualityrag.scene-release/v1","codec":"scene-palette-rgb/v1",
            "runtime_abi":"python-scene-reference/v1","decoder_sha256":decoder,"tenant":tenant,
            "index_sha256":index_sha,"source_sha256":index["header"]["source_sha256"],
            "model_sha256":index["model_object"],"grammar_sha256":digest(SCENE_GRAMMAR),
            "required_modules":{"decoder":decoder,"grammar":digest(SCENE_GRAMMAR),"model":index["model_object"]},
            "policy_ir_sha256":policy_ir_sha256,"run_id":run_id,"sequence":sequence}


def sign_release(manifest,key,*,key_id,issued_at,expires_at):
    _validate_period(issued_at,expires_at,issued_at)
    return sign({"scene_release":manifest,"issued_at":issued_at,"expires_at":expires_at},key,key_id=key_id,schema=ATTEST_SCHEMA)


class StreamSession:
    def __init__(self,store,*,signed_release,keys,expected_policy_sha256,minimum_sequence,as_of,fallback_ref):
        if not isinstance(store,ArtifactStore):raise ValueError("Scoped object store required")
        body=verify(signed_release,keys,schema=ATTEST_SCHEMA)
        if set(body)!={"scene_release","issued_at","expires_at"}:raise ValueError("Wrong release purpose")
        _validate_period(body["issued_at"],body["expires_at"],as_of)
        self.store=store;self.loads=[];self.position=0;self.paused=False;self.fallback_ref=fallback_ref
        manifest=body["scene_release"]
        index=self.load(manifest["index_sha256"])
        expected=release(manifest["index_sha256"],index,tenant=store.tenant,policy_ir_sha256=expected_policy_sha256,
                         run_id=manifest["run_id"],sequence=manifest["sequence"])
        if manifest!=expected or type(minimum_sequence) is not int or not 1<=minimum_sequence<=1_000_000_000 or manifest["sequence"]<minimum_sequence:
            raise ValueError("Release tenant, policy, model, ABI or version mismatch")
        self.index=index
        self.model=self.load(index["model_object"])
        _model(self.model)
        if digest(self.model)!=index["header"]["model_sha256"]:raise ValueError("Shared model mismatch")

    def load(self,address):
        raw=self.store.get(address)
        self.loads.append({"address":address,"bytes":len(raw)})
        return strict_json(raw,max_bytes=2_000_000)

    def pause(self):self.paused=True
    def resume(self):self.paused=False

    def seek(self,start,stop,*,variant="reference"):
        if self.paused:return {"action":"PAUSED","frames":[],"position":self.position}
        if variant not in self.index["variants"] or any(type(x) is not int for x in (start,stop)) or not 0<=start<stop<=self.index["header"]["frame_count"]:
            raise ValueError("Invalid range/variant")
        started=perf_counter_ns();before=len(self.loads)
        try:
            records=[]
            for i in range(start,stop):
                row=self.index["segments"][i]
                if row["index"]!=i or row["dependencies"]!=[self.index["model_object"]]:
                    raise ValueError("Segment dependency or ordering mismatch")
                record=self.load(row["variants"][variant])
                if record["frame_sha256"]!=row["frame_sha256"] or record["index"]!=i:raise ValueError("Segment identity mismatch")
                records.append(record)
            # Decoder range checks remain active. Supply verified inert placeholders
            # for unrequested indices; no segment data is fetched for those frames.
            payload={**self.index["header"],"frames":[{"index":i} for i in range(self.index["header"]["frame_count"])]}
            payload["frames"][start:stop]=records
            decoded=decode_frames(payload,self.model,start=start,stop=stop)
            self.position=stop
            return {"action":"PLAY","frames":decoded,"position":stop,"variant":variant,
                    "frame_times":self.index["header"]["source_frame_pts"][start:stop],
                    "seek_ns":perf_counter_ns()-started,"downloaded_segments":len(self.loads)-before,
                    "downloaded_bytes":sum(r["bytes"] for r in self.loads[before:]),
                    "can_generate":False}
        except (ValueError,KeyError,IndexError,TypeError,OSError):
            return {"action":"FALLBACK","frames":[],"reference":self.fallback_ref,
                    "reason":"SEGMENT_OR_MODEL_UNAVAILABLE","can_generate":False}


def benchmark_seek(session_factory,baseline_path,indices):
    """Observed local cold-session seeking, not a network/player performance claim."""
    from pathlib import Path
    import subprocess
    if not Path(baseline_path).is_file() or not isinstance(indices,list) or not 1<=len(indices)<=16:
        raise ValueError("Bounded local seek experiment required")
    rows=[]
    for index in indices:
        started=perf_counter_ns();session=session_factory()
        decoded=session.seek(index,index+1)
        reference_ns=perf_counter_ns()-started
        if decoded["action"]!="PLAY":raise ValueError("Reference seek unavailable")
        timestamp=session.index["header"]["source_frame_pts"][index]
        started=perf_counter_ns()
        child=subprocess.run(["ffmpeg","-nostdin","-v","error","-ss",timestamp,"-i",str(baseline_path),
            "-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-"],capture_output=True,timeout=15)
        baseline_ns=perf_counter_ns()-started
        if child.returncode:raise ValueError("Baseline seek unavailable")
        rows.append({"index":index,"scene_cold_session_ns":reference_ns,"av1_fresh_process_ns":baseline_ns,
                     "exact_frame_match":child.stdout==decoded["frames"][0],"scene_downloaded_bytes":decoded["downloaded_bytes"]})
    return {"schema":"qualityrag.local-seek-benchmark/v1","rows":rows,
            "scope":"LOCAL_FILESYSTEM_COLD_SESSION_VS_FRESH_FFMPEG_PROCESS","network_buffering":"UNMEASURED",
            "physical_device_playback":"UNMEASURED","performance_advantage":"NOT_ESTABLISHED"}


def open_stream(store,*,signed_release,keys,expected_policy_sha256,minimum_sequence,as_of,fallback_ref):
    """Host entry point: unavailable or invalid startup state selects its fallback."""
    try:
        session=StreamSession(store,signed_release=signed_release,keys=keys,
            expected_policy_sha256=expected_policy_sha256,minimum_sequence=minimum_sequence,
            as_of=as_of,fallback_ref=fallback_ref)
    except (ValueError,KeyError,IndexError,TypeError,OSError):
        return {"action":"FALLBACK","session":None,"reference":fallback_ref,
                "reason":"RELEASE_INDEX_OR_MODEL_UNAVAILABLE","can_generate":False}
    return {"action":"READY","session":session,"can_generate":False}
