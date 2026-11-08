"""Reproducible evidence-coverage evaluation over actual generated PDF/DOCX/HTML files.

No LLM is invoked: 'ungated risk' is a proxy for an application that generates
whenever any ranked chunk is returned. It is NOT a measured hallucination rate.
"""
from collections import defaultdict
from ingest_documents import OUT, parse, search
from qualityrag import evaluate

CLOCK = "2026-11-02T10:05:00Z"
REQUIRED = ("recovery-procedure", "eu-screening-control")
PACK = {"id": "eu-payments-screening-recovery", "version": "1",
        "requirements": [{"id": requirement} for requirement in REQUIRED]}

# Labels are defined by the benchmark author, not inferred by the model.
# Each tuple names a real extracted file/page and the obligation it satisfies.
LABELS = {
    "operations.pdf#page=74": "recovery-procedure",
    "eu-controls.pdf#page=187": "eu-screening-control",
}
CASES = [
    {"id": "generic-recovery", "query": "automated recovery dependency timeout on call",
     "expected": ["recovery-procedure", "eu-screening-control"]},
    {"id": "focused-eu-control", "query": "sanctions screening restoration requires compliance sign off",
     "expected": ["eu-screening-control"]},
    {"id": "unrelated-incident", "query": "prior gateway incident reduced downtime",
     "expected": ["recovery-procedure", "eu-screening-control"]},
]

def load():
    names = ("operations.pdf", "eu-controls.pdf", "old-runbook.docx", "incident.html")
    missing = [name for name in names if not (OUT/name).is_file()]
    if missing: raise RuntimeError("Generate fixtures first: python examples/enterprise-rag/build_documents.py")
    return [chunk for name in names for chunk in parse(OUT/name)]

def assess(chunks, k=3):
    results=[]
    for case in CASES:
        retrieved=search(chunks,case["query"],k)
        ids=[identifier for identifier,_,_ in retrieved]
        found={LABELS[identifier] for identifier in ids if identifier in LABELS}
        evidence=[{"id":identifier, "requirement_id":LABELS[identifier],
                   "origin":identifier.split("#")[0], "source_ref":identifier,
                   "status":"SUPPORTS", "observed_at":"2026-11-02T10:00:00Z"}
                  for identifier in ids if identifier in LABELS]
        decision=evaluate(PACK,evidence,as_of=CLOCK)
        # A deliberately weak ungated baseline answers whenever a search hit exists.
        baseline_answers=bool(ids)
        expected=set(case["expected"])
        coverage=len(found & expected)/len(expected)
        results.append({"case":case["id"],"retrieved":ids,"coverage":coverage,
                        "all_required_present":all(r in found for r in REQUIRED),
                        "baseline_answers":baseline_answers,
                        "gate_verdict":decision["verdict"],
                        "safe_abstention":decision["verdict"]=="INCONCLUSIVE" and not all(r in found for r in REQUIRED)})
    return results

def summarize(rows):
    n=len(rows)
    return {"queries":n,
            "mean_labeled_recall":round(sum(r["coverage"] for r in rows)/n,3),
            "baseline_answers_with_missing_requirements":
                sum(r["baseline_answers"] and not r["all_required_present"] for r in rows),
            "qualityrag_admissions_with_missing_requirements":
                sum(r["gate_verdict"]=="ADMIT" and not r["all_required_present"] for r in rows),
            "qualityrag_abstentions_on_missing_requirements":
                sum(r["safe_abstention"] for r in rows)}

def run():
    import json
    result=assess(load())
    print(json.dumps({"cases":result,"summary":summarize(result)},indent=2))
    assert all(r["gate_verdict"]!="ADMIT" or r["all_required_present"] for r in result)
    assert any(r["gate_verdict"]=="INCONCLUSIVE" and not r["all_required_present"] for r in result)
    return result

if __name__=="__main__":run()
