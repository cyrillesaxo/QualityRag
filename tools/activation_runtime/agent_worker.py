"""Fixed deterministic research-agent backend inside a syscall/resource sandbox.

No untrusted code is evaluated. After initialization the worker cannot open files,
create sockets/processes or import more modules. Unsupported sandbox hosts refuse.
"""
import ctypes
import errno
import json
import os
import resource
import sys

ROLES=("decomposition","grammar-compiler","activation-optimizer","packspec-guardian",
       "counterexample","ffrct-economist")


from process_sandbox import sandbox


def run(request):
    if not isinstance(request,dict) or set(request)!={"schema","role","parent_grammar_sha256","task","budget"}:
        raise ValueError("Invalid agent request")
    if request["schema"]!="qualityrag.agent-request/v1" or request["role"] not in ROLES:
        raise ValueError("Unsupported research role")
    parent=request["parent_grammar_sha256"]
    if not isinstance(parent,str) or len(parent)!=64 or any(c not in "0123456789abcdef" for c in parent):
        raise ValueError("Pinned parent grammar required")
    task=request["task"]
    if not isinstance(task,dict):raise ValueError("Typed task required")
    role=request["role"]
    if role=="decomposition":
        artifact={"components":[{"obligation":x,"state":"UNVERIFIED"} for x in task.get("obligations",[])[:32]]}
    elif role=="grammar-compiler":
        artifact={"patches":[{"op":"replace","path":"/max_ast_nodes","value":n} for n in (1,3,5,7)
                             if n<=task.get("max_ast_nodes",7)],
                  "model_patches":[{"op":"replace","path":"/palette_limit","value":n}
                                   for n in task.get("candidate_model_sizes",[])]}
    elif role=="activation-optimizer":
        modules=task.get("modules",[])
        artifact={"required_modules":sorted(set(task.get("required_modules",[]))),
                  "candidates":[{"module":m,"activation":"ON_DEMAND"} for m in modules[:32]],
                  "decoder_candidates":task.get("decoder_variants",[])}
    elif role=="packspec-guardian":
        expected=set(task.get("required_fields",[]));actual=set(task.get("preserved_fields",[]))
        missing=sorted(expected-actual)
        artifact={"decision":"BLOCK" if missing else "REQUIRES_INDEPENDENT_REVIEW",
                  "missing_fields":missing,"can_generate":False}
    elif role=="counterexample":
        cases=task.get("cases",[])[:64]
        artifact={"counterexamples":[{"case_id":r["id"],"source":r["source"],"candidate":r["candidate"]}
                     for r in cases if r["source"]!=r["candidate"]]}
    else:
        costs=task.get("costs",{})
        artifact={"known_costs":costs,"unmeasured":[k for k,v in costs.items() if v is None],
                  "advantage":"NOT_ESTABLISHED","grammar_reuse":"MEASURE_BEFORE_CLAIMING"}
    return {"schema":"qualityrag.agent-proposal/v1","role":role,"parent_grammar_sha256":parent,
            "artifact":artifact,"rationale":"Bounded deterministic "+role+" proposal",
            "backend":"DETERMINISTIC_TYPED_SEARCH","truth_status":"UNVERIFIED","can_generate":False}


try:
    raw=sys.stdin.buffer.read(262145)
    if len(raw)>262144:raise ValueError("Agent input byte budget")
    request=json.loads(raw)
    budget=request.get("budget",{})
    cpu=budget.get("cpu_seconds");memory=budget.get("memory_bytes")
    if type(cpu) is not int or not 1<=cpu<=10 or type(memory) is not int or not 64_000_000<=memory<=512_000_000:
        raise ValueError("Invalid hard resource budget")
    sandbox(cpu,memory)
    if "--probe" in sys.argv:
        denied={}
        try:
            open("/tmp/qualityrag-agent-write-probe","w")
            denied["file_open"]=False
        except PermissionError:denied["file_open"]=True
        # libc calls avoid importing socket/subprocess after filtering.
        libc=ctypes.CDLL(None)
        denied["socket"]=libc.socket(2,1,0)==-1
        denied["fork"]=libc.fork()==-1
        result={"sandbox_denied":denied}
    else:
        result=run(request)
    sys.stdout.write(json.dumps(result,sort_keys=True,allow_nan=False))
except Exception:
    sys.stderr.write("AGENT_SANDBOX_OR_INPUT_REFUSED\n")
    sys.exit(2)
