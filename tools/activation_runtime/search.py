"""Cost-bounded actual typed RCT search; identity baseline is always retained."""
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
from .common import canonical,fingerprint


def bounded_search(source,labels,grammar,*,cpu_seconds=2,memory_bytes=128_000_000,wall_seconds=5):
    if type(wall_seconds) is not int or not 1<=wall_seconds<=30:raise ValueError("Wall-clock bound")
    baseline={"regime":"stay-in-present-regime","source_sha256":fingerprint(source),"transformation":"IDENTITY"}
    raw=canonical({"source":source,"labels":labels,"grammar":grammar,"cpu_seconds":cpu_seconds,"memory_bytes":memory_bytes})
    start=perf_counter_ns()
    try:
        child=subprocess.run([sys.executable,str(Path(__file__).with_name("rct_worker.py"))],input=raw,
            capture_output=True,timeout=wall_seconds,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")},close_fds=True)
        result=json.loads(child.stdout) if child.returncode==0 and len(child.stdout)<=262144 else None
    except subprocess.TimeoutExpired:result=None
    return {"schema":"qualityrag.bounded-rct/v1","baseline":baseline,"candidate":result,
            "finite_constraint_result":result.get("structural_training_verdict","UNKNOWN") if result else "UNKNOWN",
            "reason":result.get("reason") if result else "RESOURCE_SANDBOX_OR_INPUT_BOUND",
            "discarded_candidates":"SEARCH_INCOMPLETE" if result is None or result.get("status")!="CANDIDATE" else 0,
            "budgets":{"cpu_seconds":cpu_seconds,"memory_bytes":memory_bytes,"wall_seconds":wall_seconds},
            "observed_wall_ns":perf_counter_ns()-start,"can_generate":False}
