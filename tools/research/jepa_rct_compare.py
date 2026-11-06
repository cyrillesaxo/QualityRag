"""Fail-closed, artifact-based JEPA/RCT paired comparison.

This does not train or emulate JEPA. Both candidate outputs must come from
actual independently recorded runs. It checks declared synthetic obligations,
not semantic completeness or QualityRag admission.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "qualityrag.jepa-rct-paired/v0.1"
REQUIRED = ("negation", "role", "threshold", "exception")

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def evaluate(manifest):
    if not isinstance(manifest,dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("Unsupported manifest schema")
    tasks=manifest.get("tasks")
    if not isinstance(tasks,list) or not tasks:
        raise ValueError("Nonempty tasks required")
    ids=set()
    for t in tasks:
        if not isinstance(t,dict) or not isinstance(t.get("id"),str) or t["id"] in ids:
            raise ValueError("Duplicate or invalid task id")
        ids.add(t["id"])
        if not isinstance(t.get("regime"),str) or not t["regime"]:
            raise ValueError("Regime required for every task")
        if not isinstance(t.get("gold"),dict) or not t["gold"]:
            raise ValueError("Human-reviewed gold decision fields required")
        if not isinstance(t.get("required"),list) or not t["required"] or len(set(t["required"])) != len(t["required"]):
            raise ValueError("Nonempty unique required fields")
        if not set(t["required"]).issubset(t["gold"]):
            raise ValueError("Required fields missing from gold")
    results={}
    for name in ("jepa","rct"):
        candidate=manifest.get("candidates",{}).get(name)
        if not isinstance(candidate,dict) or candidate.get("status") != "MEASURED":
            results[name]={"status":"NOT_EVALUATED","reason":"Actual recorded run required"}
            continue
        if not all(isinstance(candidate.get(k),str) and candidate[k] for k in ("artifact_sha256","model_or_grammar_version","run_ref")):
            results[name]={"status":"NOT_EVALUATED","reason":"Missing reproducible run provenance"}
            continue
        responses=candidate.get("responses")
        if not isinstance(responses,dict) or set(responses)!=ids:
            results[name]={"status":"INVALID","reason":"Missing or extra task responses"}
            continue
        incorrect=[];checked=0
        for task in tasks:
            out=responses[task["id"]]
            if not isinstance(out,dict):
                incorrect.append(task["id"]+":invalid_response")
                continue
            for field in task["required"]:
                checked+=1
                if field not in out or type(out[field]) is not type(task["gold"][field]) or out[field]!=task["gold"][field]:
                    incorrect.append(task["id"]+":"+field)
        results[name]={"status":"EVALUATED","required_field_checks":checked,
                       "violations":incorrect,"violation_count":len(incorrect),
                       "all_declared_checks_pass":not incorrect,
                       "run_ref":candidate["run_ref"],
                       "artifact_sha256":candidate["artifact_sha256"]}
    comparison="UNAVAILABLE"
    if all(results[n]["status"]=="EVALUATED" for n in ("jepa","rct")):
        comparison="PAIRED_DECLARED_FIELDS_ONLY"
    return {"schema":"qualityrag.jepa-rct-paired-result/v0.1",
            "manifest_sha256":fingerprint(manifest),"comparison_status":comparison,
            "results":results,"qualityrag_admission":"INCONCLUSIVE",
            "limitations":["Field equality is not proof of semantic sufficiency",
                           "User-supplied run provenance is not cryptographically authenticated",
                           "No latency/cost claim without independently measured resources",
                           "Regime boundary generalization requires separate held-out tests"]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("manifest",type=Path)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    report=evaluate(json.loads(args.manifest.read_text(encoding="utf-8")))
    formatted=json.dumps(report,indent=2,sort_keys=True)+"\n"
    if args.out: args.out.write_text(formatted,encoding="utf-8")
    else: print(formatted,end="")

if __name__=="__main__":
    main()
