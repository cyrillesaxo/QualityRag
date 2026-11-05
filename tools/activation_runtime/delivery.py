"""Criterion-level review packet from the audited inventory; never self-approves stories."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from .audit import audit


def report(root=None,*,trust=None,as_of=None):
    root=Path(__file__).resolve().parents[2] if root is None else Path(root)
    checked=audit(root,trust=trust,as_of=as_of)
    path=root/"tools/activation_runtime/capabilities.json";inventory=json.loads(path.read_text())
    stories=[]
    for item in inventory["stories"]:
        stories.append({"story_id":item["story_id"],"title":item["title"],"acceptance_status":item["status"],
            "software_status":item["engineering_status"],"criteria":item["criteria"],
            "implementation_files":item["modules"],"runnable_evidence":item["test_or_receipt"],
            "remaining_acceptance_requirement":item["remaining"],"independent_validation":item["independent_validation"]})
    return {"schema":"qualityrag.story-delivery-report/v1","scope":"AUDITED_SOURCE_INVENTORY_NOT_A_TEST_OR_ACCEPTANCE_RECEIPT",
            "source_inventory_sha256":sha256(path.read_bytes()).hexdigest(),"requirements_sha256":sha256((root/"FR.MD").read_bytes()).hexdigest(),
            "counts":checked["counts"],"criterion_count":sum(len(s["criteria"]) for s in stories),"stories":stories,
            "integrated_workflow_stories":[s["story_id"] for s in stories if s["software_status"]=="INTEGRATED_REVIEWED_FINITE_WORKFLOW"],
            "acceptance_authority":"US-001/002 use their criterion-specific live GitHub source/CI acceptance; all other DONE entries retain independent signed completion. This report grants no approval."}


def markdown(value):
    text=["# User-story delivery and acceptance packet","",
        "This is an audited source inventory, not a claim that every acceptance criterion passed.",
        "Software delivery and formal acceptance are shown separately. Test paths identify runnable",
        "evidence; independent review, real measurements and external sources are not inferred from code.","",
        "| Story | Software status | Acceptance status | Remaining acceptance requirement |","|---|---|---|---|"]
    for s in value["stories"]:
        cell=lambda v:str(v).replace("|","\\|").replace("\n"," ")
        text.append("| "+" | ".join(map(cell,(s["story_id"]+" — "+s["title"],s["software_status"],s["acceptance_status"],s["remaining_acceptance_requirement"])))+" |")
    for s in value["stories"]:
        text.extend(["", "## "+s["story_id"]+" — "+s["title"],"", "Runnable evidence: "+s["runnable_evidence"],""])
        for c in s["criteria"]:text.append(str(c["number"])+". "+c["text"]+" — "+c["acceptance"])
        text.extend(["","Remaining: "+s["remaining_acceptance_requirement"]])
    return "\n".join(text)+"\n"


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",required=True)
    parser.add_argument("--trust",help="reviewer trust store (default: the repository's reviewer-trust.json)")
    parser.add_argument("--as-of");args=parser.parse_args()
    trust=None
    if args.trust:
        from .audit import load_trust
        trust=load_trust(args.trust)
    value=report(trust=trust,as_of=args.as_of);out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    (out/"stories.json").write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
    (out/"stories.md").write_text(markdown(value))
    print(json.dumps({"stories":len(value["stories"]),"criteria":value["criterion_count"],"report":str(out/"stories.md"),"counts":value["counts"]}))


if __name__=="__main__":main()
