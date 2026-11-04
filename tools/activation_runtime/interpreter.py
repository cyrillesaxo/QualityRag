"""Finite activation DSL interpreter. No eval, plugins, dynamic module names or callbacks."""
from copy import deepcopy
from .common import fingerprint
from .preservation import audit_output
from .pipeline import encode
from finite_activation import parse_source


def execute_plan(raw, *, plan, contract, ir, max_steps=32):
    source=parse_source(raw)
    if type(max_steps) is not int or not 1<=max_steps<=32 or not isinstance(plan,list) or not 1<=len(plan)<=max_steps:
        raise ValueError("Bounded operator sequence required")
    state=deepcopy(source)
    trace=[]
    checks=[]
    obligations={row["field"] for row in contract["obligations"]}
    verified=False
    fallback_used=False
    requires_fallback=False
    mapping={field:field for field in source}
    for index,op in enumerate(plan):
        if not isinstance(op,dict):
            raise ValueError("Typed operator required")
        name=op.get("op")
        before=fingerprint(state)
        if requires_fallback and name!="FALLBACK":
            return {"action":"REFUSE","output":None,"trace":trace,"can_generate":False,"reason":"VERIFICATION_FAILED_NO_FALLBACK","finite_constraint_result":"UNSAT","checks":checks}
        if name=="PRESERVE" and set(op)=={"op","fields"}:
            if not isinstance(op["fields"],list) or set(op["fields"])!=obligations:
                raise ValueError("Preservation inventory differs from reviewed contract")
        elif name=="TRANSITION" and set(op)=={"op","mapping"}:
            mapping=op["mapping"]
            artifact=encode(raw,mapping)
            # Execute a real finite transition and reverse it under the pinned mapping.
            transformed=artifact["payload"]
            state={field:transformed[target] for field,target in artifact["mapping"].items()}
            verified=False
        elif name=="ACTIVATE" and set(op) in ({"op","runtime"},{"op","runtime","payload"}) and op["runtime"]=="finite-json/v1":
            if "payload" in op:
                candidate=op["payload"]
                if not isinstance(candidate,dict) or set(candidate)!=set(mapping.values()):
                    raise ValueError("Activation payload does not match compiled mapping")
                state={field:candidate[target] for field,target in mapping.items()}
                verified=False
            else:state=deepcopy(state)
        elif name=="VERIFY" and set(op)=={"op"}:
            audit=audit_output(raw,state,contract,current_ir=ir)
            checks.append(audit)
            verified=audit["finite_constraint_result"]=="SAT"
            if not verified:
                requires_fallback=True
        elif name=="FALLBACK" and set(op)=={"op","baseline"} and op["baseline"]=="original-source":
            if fallback_used: raise ValueError("At most one fallback")
            fallback_used=True
            requires_fallback=False
            # Fallback is independently checked against the same contract and IR.
            state=deepcopy(source)
            verified=audit_output(raw,state,contract,current_ir=ir)["finite_constraint_result"]=="SAT"
        else:
            raise ValueError("Unsupported operator/options")
        trace.append({"step":index,"operator":name,"before_sha256":before,"after_sha256":fingerprint(state)})
    return {"action":"REQUIRES_REVIEW" if verified else "REFUSE",
            "output":state if verified else None,"trace":trace,"can_generate":False,
            "qualityrag_admission":"INCONCLUSIVE","finite_constraint_result":"SAT" if verified else ("UNSAT" if checks and checks[-1]["finite_constraint_result"]=="UNSAT" else "UNKNOWN"),"fallback_used":fallback_used,"checks":checks}


def exhaustive_equivalence(before,after, *, nodes, relations):
    """Every node-pair query in a bounded explicitly declared relation vocabulary."""
    if (not isinstance(nodes,list) or not 1<=len(nodes)<=64 or len(set(nodes))!=len(nodes)
            or not isinstance(relations,list) or not 1<=len(relations)<=16):
        raise ValueError("Finite unique nodes/relations required")
    def checked(rows):
        if not isinstance(rows,list) or len(rows)>4096: raise ValueError("Graph budget")
        out=set()
        for row in rows:
            if not isinstance(row,list) or len(row)!=3 or row[0] not in nodes or row[2] not in nodes or row[1] not in relations:
                raise ValueError("Undeclared graph endpoint or relation")
            out.add(tuple(row))
        return out
    left,right=checked(before),checked(after)
    counterexamples=[]
    for subject in nodes:
        for relation in relations:
            for target in nodes:
                triple=(subject,relation,target)
                if (triple in left)!=(triple in right):
                    counterexamples.append({"subject":subject,"relation":relation,"object":target,
                                            "before":triple in left,"after":triple in right})
    return {"finite_constraint_result":"UNSAT" if counterexamples else "SAT",
            "checked_queries":len(nodes)**2*len(relations),"counterexamples":counterexamples,
            "scope":"DECLARED_FINITE_GRAPH_ONLY","can_generate":False}
