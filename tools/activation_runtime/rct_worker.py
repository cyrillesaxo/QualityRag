"""One-shot canonical typed RCT search under default-deny seccomp/RLIMIT."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"semantic_store"))
from rct_typed_grammar import induce_typed_rule
from process_sandbox import sandbox

try:
    raw=sys.stdin.buffer.read(262145)
    if len(raw)>262144:raise ValueError("Input budget")
    request=json.loads(raw)
    if set(request)!={"source","labels","grammar","cpu_seconds","memory_bytes"}:raise ValueError("Typed bounded RCT request")
    cpu=request["cpu_seconds"];memory=request["memory_bytes"]
    if type(cpu) is not int or not 1<=cpu<=10 or type(memory) is not int or not 64_000_000<=memory<=512_000_000:raise ValueError("Resource limits")
    sandbox(cpu,memory)
    result=induce_typed_rule(request["source"],request["labels"],request["grammar"])
    sys.stdout.write(json.dumps(result,allow_nan=False,sort_keys=True))
except Exception:
    sys.stderr.write("RCT_BOUNDED_SEARCH_REFUSED\n");sys.exit(2)
