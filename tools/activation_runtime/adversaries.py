"""Finite distinction challenge corpus and explicit false-accept accounting."""
from copy import deepcopy
from .common import fingerprint

BASE={"actor":"supplier","recipient":"buyer","polarity":"NOT","time":"before",
      "quantity":1,"unit":"mg","caption":"STOP","model":"model-v1"}
MUTATIONS={"actor-recipient":("actor","buyer"),"negation":("polarity",""),
           "temporal":("time","after"),"units":("unit","g"),
           "quantity":("quantity",1000),"captions":("caption","GO"),
           "incompatible-model":("model","model-v2")}


def corpus():
    cases=[]
    for name,(field,value) in MUTATIONS.items():
        candidate={**BASE,field:value}
        cases.append({"id":name,"family":name,"source":deepcopy(BASE),"candidate":candidate,
                      "expected":"UNSAT","critical":True})
    cases.append({"id":"control","family":"control","source":deepcopy(BASE),
                  "candidate":deepcopy(BASE),"expected":"SAT","critical":False})
    return cases


def challenge(evaluator,cases):
    rows=[]
    for case in cases:
        result=evaluator(case["source"],case["candidate"])
        if result not in {"SAT","UNSAT","UNKNOWN"}:raise ValueError("Invalid finite evaluator verdict")
        rows.append({"case":case["id"],"expected":case["expected"],"observed":result,"critical":case["critical"]})
    bad=[r for r in rows if r["expected"]=="UNSAT"]
    false_accept=sum(r["observed"]=="SAT" for r in bad)
    missed=sum(r["observed"]!="UNSAT" for r in bad)
    return {"schema":"qualityrag.adversarial-gate/v1","cases_sha256":fingerprint(cases),"rows":rows,
            "false_accept_rate":false_accept/len(bad) if bad else None,
            "missed_counterexample_rate":missed/len(bad) if bad else None,
            "critical_regressions":sum(r["critical"] and r["observed"]!="UNSAT" for r in rows),
            "promotion":"BLOCK" if missed else "REQUIRES_INDEPENDENT_REVIEW",
            "can_promote":False,"scope":"FINITE_AUTHORED_DISTINCTIONS_ONLY"}
