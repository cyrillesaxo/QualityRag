"""Reproduce authored engineering evidence; never substitutes a real corpus/pilot.

The receipt records the exact invocation, input and environment digests, and a
comparison of the live runtime with research/environment.lock.json. A missing
dependency marks the affected components SKIP with the reason; it is never
reported as a pass.
"""
import argparse
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from .demo import run as run_finite
from .experiments import run_codec_arms,paired_interval
from .agents import research_round,ROLES
from .adversaries import corpus,challenge
from .common import fingerprint
from .pilot import measure
from .scene_codec import train_model,encode
from .release import readiness,REQUIRED

HERE=Path(__file__).resolve().parent
LOCK=HERE/"research/environment.lock.json"
INPUTS=["fixtures/packspec.json","fixtures/grammar.json","fixtures/source.json","fixtures/transform.json",
        "research/protocol.json","research/environment.lock.json"]


def _version(command):
    try:
        out=subprocess.run(command,capture_output=True,text=True,timeout=10)
        return out.stdout.splitlines()[0].strip() if out.returncode==0 and out.stdout else None
    except (OSError,subprocess.SubprocessError):
        return None


def environment(lock_path=LOCK,*,which=shutil.which):
    """Compare the live runtime with the pinned lock; mismatches are reported, never hidden."""
    lock=json.loads(Path(lock_path).read_text())
    live={"python":platform.python_version(),"platform":platform.system(),"machine":platform.machine(),
          "ffmpeg":_version(["ffmpeg","-version"]) if which("ffmpeg") else None,
          "node":_version(["node","--version"]) if which("node") else None,"packages":{}}
    for name in lock.get("packages",{}):
        try:live["packages"][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:live["packages"][name]=None
    mismatches=[]
    for key in ("python","platform","machine","ffmpeg","node"):
        if lock.get(key)!=live[key]:mismatches.append({"item":key,"pinned":lock.get(key),"live":live[key]})
    for name,version in lock.get("packages",{}).items():
        if live["packages"][name]!=version:mismatches.append({"item":"package:"+name,"pinned":version,"live":live["packages"][name]})
    return {"lock_sha256":sha256(Path(lock_path).read_bytes()).hexdigest(),"live":live,
            "matches_lock":not mismatches,"mismatches":mismatches,
            "missing_tools":sorted(t for t in ("ffmpeg","node") if live[t] is None)}


def run(output,*,argv=None,which=shutil.which):
    root=Path(output);root.mkdir(parents=True,exist_ok=False)
    env=environment(which=which)
    components={};skipped=[]
    def skip(name,reason):
        components[name]={"status":"SKIP","reason":reason};skipped.append(name)
    finite=run_finite(root/"finite")
    components["finite"]={"status":"RAN","cases":len(finite["cases"])}
    adversaries=challenge(lambda a,b:"SAT" if fingerprint(a)==fingerprint(b) else "UNSAT",corpus())
    components["adversaries"]={"status":"RAN"}
    tasks={role:{} for role in ROLES}
    tasks["decomposition"]={"obligations":["source-custody","NOT","units"]}
    tasks["packspec-guardian"]={"required_fields":["NOT","units"],"preserved_fields":["units"]}
    tasks["counterexample"]={"cases":[{"id":"negation","source":"NOT","candidate":""}]}
    agents=research_round({"schema":"typed-search/v1"},tasks)
    components["agents"]={"status":"RAN"}
    ablation=device=None
    if which("ffmpeg") is None:
        for name in ("clips","ablation","host_device"):skip(name,"DEPENDENCY_UNAVAILABLE:ffmpeg")
    else:
        clips=root/"clips";clips.mkdir()
        names=("train-one","train-two","heldout-one","heldout-two")
        paths=[]
        for index,name in enumerate(names):
            path=clips/(name+".mkv")
            subprocess.run(["ffmpeg","-nostdin","-v","error","-n","-f","lavfi","-i","testsrc2=size=64x64:rate=4",
                "-vf","hue=h="+str(index*73),"-t","1","-c:v","ffv1","-fflags","+bitexact","-flags:v","+bitexact",
                "-map_metadata","-1",str(path)],capture_output=True,check=True,timeout=20)
            paths.append(path)
        components["clips"]={"status":"RAN","sha256":[sha256(p.read_bytes()).hexdigest() for p in paths]}
        ablation=run_codec_arms(paths[:2],paths[2:],root/"ablation");components["ablation"]={"status":"RAN"}
        model=train_model(paths[:2]);payload,_=encode(paths[2],model)
        device=measure(payload,model,device_class="host-cpu",max_memory_bytes=128_000_000,max_latency_ns=5_000_000_000)
        components["host_device"]={"status":"RAN"}
    report={"schema":"qualityrag.engineering-research-receipts/v1","scope":"AUTHORED_SYNTHETIC_ENGINEERING_ONLY",
        "invocation":{"module":"tools.activation_runtime.run_research","argv":list(argv) if argv is not None else ["--out",str(output)]},
        "inputs":{path:sha256((HERE/path).read_bytes()).hexdigest() for path in INPUTS if (HERE/path).exists()},
        "environment":env,"components":components,
        "result":"INCOMPLETE" if skipped else ("COMPLETE" if env["matches_lock"] else "COMPLETE_ENVIRONMENT_MISMATCH"),
        "skipped":skipped,
        "finite_cases":len(finite["cases"]),"ablation":ablation,"adversaries":adversaries,"agents":agents,
        "host_device":device,
        "release":readiness({k:None for k in REQUIRED},critical_field_failures=0,total_cost_comparison="UNKNOWN"),
        "licensed_100_clip_corpus":"NOT_SUPPLIED","physical_mobile_tv_devices":"NOT_MEASURED",
        "qualified_independent_review":"NOT_SUPPLIED","learned_baseline":"PINNED_LICENSED_WEIGHTS_REQUIRED",
        "can_generate":False,"can_claim_semantic_compression_advantage":False}
    (root/"receipt.json").write_text(json.dumps(report,sort_keys=True,indent=2))
    return report


def main(argv=None):
    argv=sys.argv[1:] if argv is None else list(argv)
    parser=argparse.ArgumentParser();parser.add_argument("--out",required=True)
    args=parser.parse_args(argv);result=run(args.out,argv=argv)
    summary=json.dumps({"receipt":str(Path(args.out)/"receipt.json"),"scope":result["scope"],"result":result["result"],
                        "skipped":result["skipped"],"environment_matches_lock":result["environment"]["matches_lock"],
                        "release":result["release"]["decision"]},sort_keys=True)
    # The exact stdout is kept next to the receipt so the run can be compared byte for byte.
    (Path(args.out)/"stdout.json").write_text(summary+"\n")
    print(summary)


if __name__=="__main__":main()
