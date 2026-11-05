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
    spec=grammar if isinstance(grammar,dict) else {}
    enumerated=result.get("enumerated_candidates") if result else None
    selected=1 if result and result.get("status")=="CANDIDATE" else 0
    if type(enumerated) is int:
        # Every enumerated typed AST other than the selected minimum was discarded.
        discarded={"enumerated":enumerated,"selected":selected,"discarded":max(enumerated-selected,0),
                   "minimal_candidate_count":result.get("minimal_candidate_count")}
    else:
        discarded={"enumerated":"UNKNOWN","selected":0,"discarded":"UNKNOWN","reason":"SEARCH_INCOMPLETE"}
    return {"schema":"qualityrag.bounded-rct/v1","baseline":baseline,"candidate":result,
            "finite_constraint_result":result.get("structural_training_verdict","UNKNOWN") if result else "UNKNOWN",
            "reason":result.get("reason") if result else "RESOURCE_SANDBOX_OR_INPUT_BOUND",
            "discarded_candidates":discarded,
            "budgets":{"cpu_seconds":cpu_seconds,"memory_bytes":memory_bytes,"wall_seconds":wall_seconds,
                       # Candidate-count and depth limits are enforced by the reused typed grammar.
                       "max_candidates":spec.get("max_candidates"),"max_ast_nodes":spec.get("max_ast_nodes")},
            "observed_wall_ns":perf_counter_ns()-start,"can_generate":False}
