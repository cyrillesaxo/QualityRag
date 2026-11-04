"""Reproduce authored engineering evidence; never substitutes a real corpus/pilot."""
import argparse
import json
from pathlib import Path
import subprocess

from .demo import run as run_finite
from .experiments import run_codec_arms,paired_interval
from .agents import research_round,ROLES
from .adversaries import corpus,challenge
from .common import fingerprint
from .pilot import measure
from .scene_codec import train_model,encode
from .release import readiness,REQUIRED


def run(output):
    root=Path(output);root.mkdir(parents=True,exist_ok=False)
    finite=run_finite(root/"finite")
    clips=root/"clips";clips.mkdir()
    names=("train-one","train-two","heldout-one","heldout-two")
    paths=[]
    for index,name in enumerate(names):
        path=clips/(name+".mkv")
        subprocess.run(["ffmpeg","-nostdin","-v","error","-n","-f","lavfi","-i","testsrc2=size=64x64:rate=4",
            "-vf","hue=h="+str(index*73),"-t","1","-c:v","ffv1","-fflags","+bitexact","-flags:v","+bitexact",
            "-map_metadata","-1",str(path)],capture_output=True,check=True,timeout=20)
        paths.append(path)
    ablation=run_codec_arms(paths[:2],paths[2:],root/"ablation")
    adversaries=challenge(lambda a,b:"SAT" if fingerprint(a)==fingerprint(b) else "UNSAT",corpus())
    tasks={role:{} for role in ROLES}
    tasks["decomposition"]={"obligations":["source-custody","NOT","units"]}
    tasks["packspec-guardian"]={"required_fields":["NOT","units"],"preserved_fields":["units"]}
    tasks["counterexample"]={"cases":[{"id":"negation","source":"NOT","candidate":""}]}
    agents=research_round({"schema":"typed-search/v1"},tasks)
    model=train_model(paths[:2]);payload,_=encode(paths[2],model)
    device=measure(payload,model,device_class="host-cpu",max_memory_bytes=128_000_000,max_latency_ns=5_000_000_000)
    report={"schema":"qualityrag.engineering-research-receipts/v1","scope":"AUTHORED_SYNTHETIC_ENGINEERING_ONLY",
        "finite_cases":len(finite["cases"]),"ablation":ablation,"adversaries":adversaries,"agents":agents,
        "host_device":device,
        "release":readiness({k:None for k in REQUIRED},critical_field_failures=0,total_cost_comparison="UNKNOWN"),
        "licensed_100_clip_corpus":"NOT_SUPPLIED","physical_mobile_tv_devices":"NOT_MEASURED",
        "qualified_independent_review":"NOT_SUPPLIED","learned_baseline":"PINNED_LICENSED_WEIGHTS_REQUIRED",
        "can_generate":False,"can_claim_semantic_compression_advantage":False}
    (root/"receipt.json").write_text(json.dumps(report,sort_keys=True,indent=2))
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",required=True)
    args=parser.parse_args();result=run(args.out)
    print(json.dumps({"receipt":str(Path(args.out)/"receipt.json"),"scope":result["scope"],"release":result["release"]["decision"]}))


if __name__=="__main__":main()
