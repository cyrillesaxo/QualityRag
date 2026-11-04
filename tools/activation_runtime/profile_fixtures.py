"""Distinct authored domain PackSpecs and source-anchored preservation contracts."""
import json
from pathlib import Path
from .common import canonical
from .preservation import make_contract
from compiler import inspect
from typed_ir import compile_ir

SOURCES={
"education":{"question":"Select every item EXCEPT B.","exception":"B","learner_attempt":"UNKNOWN"},
"clinical-description":{"symptom_quote":"My chest hurts when I run.","context_quote":"when I run","diagnosis":None},
"nursing":{"instruction":"The exam asks which action is NOT permitted.","quantity":1,"unit":"mg","actor":"learner"},
"legal":{"actor":"alice","recipient":"bob","obligation":"pay","modality":"MUST","polarity":"NOT"},
"video":{"frame_sha256":"a"*64,"pts":"0","subtitle_text":"NOT EXCEPT","identity":"UNKNOWN"}
}


def generate(output):
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    results={}
    for domain,source in SOURCES.items():
        target=root/domain;target.mkdir(exist_ok=True)
        policy={"pack_id":"profile-"+domain,"version":"1.0",
                "requirements":["Independent custody evidence for "+field+" is required." for field in source]}
        source_file=target/"policy-source.json";source_file.write_bytes(canonical(policy))
        report=inspect(source_file)
        candidates=report["candidate_constraints"]
        rules=[];obligations=[]
        for field,value in source.items():
            matching=[c for c in candidates if "for "+field+" is required." in c["quotation"]]
            if len(matching)!=1:raise ValueError("Ambiguous profile source extraction")
            node="field-"+field
            rules.append({"candidate_id":matching[0]["candidate_id"],"node_id":node,"kind":"EVIDENCE_PRESENCE",
                "parameters":{"requirement_id":node,"min_independent_sources":1},"approved":True,
                "reviewed_by":"AUTHORED_FIXTURE_LABEL_ONLY","rationale":"Separate domain preservation fixture; independent reviewer authority is not supplied"})
            obligations.append({"field":field,"ir_node_id":node,
                "mode":"UNKNOWN" if value is None or value=="UNKNOWN" else "EXACT",
                "tolerance":None,"omission_permitted":False})
        ir=compile_ir(report,{"schema":"qualityrag.typed-mapping/v1","source_sha256":report["source"]["sha256"],"rules":rules})
        raw=canonical(source)
        contract=make_contract(raw,task=domain,author="fixture-author",reviewer="independent-review-required",
                               tenant="research",ir=ir,obligations=obligations)
        (target/"source.json").write_bytes(raw)
        for name,value in (("ir",ir),("contract",contract)):
            (target/(name+".json")).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
        results[domain]={"source":source,"ir":ir,"contract":contract,
                        "scope":"AUTHORED_FIXTURE_NOT_INDEPENDENTLY_VALIDATED"}
    return results


if __name__=="__main__":generate(Path(__file__).with_name("profiles"))
