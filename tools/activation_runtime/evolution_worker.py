"""Bounded real encode/activation experiment in the existing syscall sandbox."""
import base64
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from evolution_program import encode,decode,canonical,MAX_SOURCE
from process_sandbox import sandbox
from time import perf_counter_ns
from hashlib import sha256
try:
    request=json.loads(sys.stdin.buffer.read(1_000_001))
    raw=base64.b64decode(request["source"],validate=True)
    if len(raw)>MAX_SOURCE:raise ValueError("Source budget")
    for name in ("evolution.py","evolution_worker.py","evolution_program.py","process_sandbox.py"):
        if request["code_sha256"][name]!=sha256(Path(__file__).with_name(name).read_bytes()).hexdigest():raise ValueError("Evaluator pin")
    if request["python_version"]!=sys.version:raise ValueError("Runtime pin")
    # Imports/initialization precede syscall filtering; untrusted grammar is inert.
    sandbox(3,256_000_000)
    packet,encoding=encode(raw,request["program"])
    first,activation=decode(packet,indices=[0])
    output,verification=decode(packet)
    if output!=raw:raise ValueError("Required exact source distinction lost")
    # The grammar and activation metadata are included in actual candidate bytes.
    install=request["decoder_install_bytes"]
    if install is not None and (type(install) is not int or not 0<=install<=2**53):raise ValueError("Runtime cost bound")
    choose=install is not None and len(packet)+install<len(raw)
    selected=packet if choose else raw
    result={"schema":"qualityrag.grammar-experiment/v1","finite_constraint_result":"SAT",
            "source_sha256":sha256(raw).hexdigest(),"output_sha256":sha256(output).hexdigest(),
            "baseline_bytes":len(raw),"selected_bytes":len(selected)+(install if choose else 0),
            "payload_bytes":len(selected),"candidate_bytes":len(packet),"decoder_install_bytes":install,
            "runtime_cost_basis":"HOST_DECLARED_NOT_INDEPENDENTLY_VERIFIED" if install is not None else "UNKNOWN_FALLBACK_REQUIRED",
            "activation_scope":"CANDIDATE_PROGRAM_ONLY_BASELINE_DECODER_UNMEASURED",
            "fallback":selected is raw,"encoding":encoding,"activation":activation,"verification":verification,
            "selected_payload":base64.b64encode(selected).decode(),"energy_j":None,
            "qualityrag_admission":"INCONCLUSIVE","can_generate":False}
    sys.stdout.write(json.dumps(result,sort_keys=True,allow_nan=False))
except Exception:
    sys.stderr.write("GRAMMAR_EXPERIMENT_REFUSED\n");sys.exit(2)
