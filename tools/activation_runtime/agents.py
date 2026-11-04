"""Parallel bounded research roles; hidden holdouts are never sent to proposers."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
from .common import canonical, fingerprint

ROLES=("decomposition","grammar-compiler","activation-optimizer","packspec-guardian",
       "counterexample","ffrct-economist")


def propose(role,*,parent_grammar,task,cpu_seconds=2,memory_bytes=128_000_000,wall_seconds=5,input_token_limit=32768):
    if role not in ROLES or type(wall_seconds) is not int or not 1<=wall_seconds<=30:
        raise ValueError("Unsupported role or wall-clock budget")
    from jsonschema import Draft202012Validator
    schema=json.loads((Path(__file__).with_name("roles")/(role+".json")).read_text())
    from jsonschema.exceptions import ValidationError
    try:
        Draft202012Validator(schema).validate(task)
    except ValidationError as exc:
        raise ValueError("Task differs from versioned role contract") from exc
    request={"schema":"qualityrag.agent-request/v1","role":role,
             "parent_grammar_sha256":fingerprint(parent_grammar),"task":task,
             "budget":{"cpu_seconds":cpu_seconds,"memory_bytes":memory_bytes}}
    raw=canonical(request)
    if type(input_token_limit) is not int or input_token_limit<1 or len(raw)>input_token_limit*4:
        raise ValueError("Input budget exhausted")
    start=perf_counter_ns()
    try:
        child=subprocess.run([sys.executable,str(Path(__file__).with_name("agent_worker.py"))],
            input=raw,capture_output=True,timeout=wall_seconds,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")},
            close_fds=True,check=False)
    except subprocess.TimeoutExpired:
        return {"status":"UNKNOWN","reason":"WALL_BUDGET_EXHAUSTED","role":role}
    if child.returncode or len(child.stdout)>262144:
        return {"status":"UNKNOWN","reason":"SANDBOX_OR_INPUT_REFUSED","role":role}
    proposal=json.loads(child.stdout)
    if proposal.get("parent_grammar_sha256")!=request["parent_grammar_sha256"] or proposal.get("role")!=role:
        raise ValueError("Agent proposal binding mismatch")
    return {"status":"PROPOSAL","proposal":proposal,"elapsed_ns":perf_counter_ns()-start,
            "input_bytes":len(raw),"provider_tokens":None,"provider_cost":"NOT_APPLICABLE_DETERMINISTIC",
            "sandbox":"SECCOMP_DEFAULT_DENY_AND_RLIMIT"}


def research_round(parent_grammar,tasks):
    if not isinstance(tasks,dict) or set(tasks)!=set(ROLES):raise ValueError("All six distinct role contracts required")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures={role:pool.submit(propose,role,parent_grammar=parent_grammar,task=tasks[role]) for role in ROLES}
        results={role:futures[role].result() for role in ROLES}
    guardian=results["packspec-guardian"]
    blocked=(guardian.get("status")!="PROPOSAL" or guardian["proposal"]["artifact"]["decision"]!="REQUIRES_INDEPENDENT_REVIEW")
    counter=results["counterexample"]
    disagreement=(counter.get("status")=="PROPOSAL" and bool(counter["proposal"]["artifact"]["counterexamples"]))
    return {"schema":"qualityrag.agent-round/v1","results":results,
            "decision":"BLOCK" if blocked or disagreement else "REQUIRES_INDEPENDENT_REVIEW",
            "disagreement":disagreement,"can_promote":False,"can_generate":False}


def schedule(experiments,*,budget):
    from fractions import Fraction
    from .common import identity
    import math
    def amount(value):
        try:valid=type(value) in (int,float) and math.isfinite(value) and value>=0
        except OverflowError:valid=False
        if not valid:raise ValueError("Nonnegative finite investigation value required")
        return Fraction(str(value))
    remaining=amount(budget)
    if not isinstance(experiments,list) or len(experiments)>128:raise ValueError("Bounded experiment set")
    costs={};values={}
    for item in experiments:
        if not isinstance(item,dict) or set(item)!={"id","expected_value","cost"}:raise ValueError("Explicit experiment value and cost required")
        identity(item["id"])
        if item["id"] in costs:raise ValueError("Duplicate experiment ID")
        costs[item["id"]]=amount(item["cost"]);values[item["id"]]=amount(item["expected_value"])
        if not costs[item["id"]]:raise ValueError("Positive experiment cost required")
    ordered=sorted(experiments,key=lambda x:(-values[x["id"]]/costs[x["id"]],x["id"]))
    selected=[]
    for item in ordered:
        cost=costs[item["id"]]
        if cost<=remaining:
            selected.append(item["id"]);remaining-=cost
    return {"selected":selected,"remaining_budget":float(remaining),"skipped":[x["id"] for x in ordered if x["id"] not in selected]}
