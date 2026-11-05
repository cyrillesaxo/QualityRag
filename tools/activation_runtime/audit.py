"""Coverage audit: objective inventory/catalog evidence, independent signed research acceptance."""
from hashlib import sha256
import json
from pathlib import Path
import re
from .common import fingerprint,HEX


def _completion(item,keys,as_of):
    from .authority import ATTEST_SCHEMA,verify,_validate_period
    body=verify(item["completion_envelope"],keys,schema=ATTEST_SCHEMA)
    if set(body)!={"completion","issued_at","expires_at"}:raise ValueError("Wrong completion purpose")
    _validate_period(body["issued_at"],body["expires_at"],as_of)
    receipt=body["completion"]
    if not isinstance(item.get("implementation_commit"),str) or not re.fullmatch("[0-9a-f]{40}",item["implementation_commit"]):
        raise ValueError("Exact implementation commit required")
    expected={"schema":"qualityrag.story-completion/v1","story_id":item["story_id"],
              "implementation_commit":item["implementation_commit"],
              "module_inventory_sha256":fingerprint(item["modules"]),
              "acceptance_sha256":item["acceptance_sha256"]}
    if any(receipt.get(k)!=v for k,v in expected.items()):raise ValueError("Completion source or criteria mismatch")
    if not re.fullmatch("[0-9a-f]{40}",receipt.get("merge_commit","")):raise ValueError("Merged review evidence required")
    ci=receipt.get("ci",{})
    if (ci.get("status")!="PASSED" or ci.get("commit")!=item["implementation_commit"]
            or not HEX.fullmatch(ci.get("receipt_sha256",""))
            or not ci.get("url","").startswith("https://github.com/")):
        raise ValueError("Passing commit-bound CI evidence required")
    if receipt.get("all_acceptance_criteria")!="MET":
        raise ValueError("Independent acceptance is incomplete")


def audit(root=None,*,reviewer_keys=None,as_of=None):
    root=Path(__file__).resolve().parents[2] if root is None else Path(root)
    inventory=json.loads((root/"tools/activation_runtime/capabilities.json").read_text())
    stories=inventory["stories"];wanted={"US-"+str(n).zfill(3) for n in range(1,52)}
    actual=[x["story_id"] for x in stories]
    if len(actual)!=51 or len(set(actual))!=51 or set(actual)!=wanted:raise ValueError("Missing or duplicate story coverage")
    content=(root/"FR.MD").read_text()
    declared=set("US-"+x for x in re.findall(r"\*\*US-(\d{3}) ·",content))
    if declared!=wanted:raise ValueError("Inventory differs from FR.MD")
    criteria={"US-"+number:sha256(text.strip().encode()).hexdigest() for number,text in re.findall(
        r"\*\*US-(\d{3}) ·[^\n]+\n.*?\*\*Acceptance:\*\* ([^\n]+)",content,re.S)}
    administrative=[]
    for item in stories:
        if item.get("acceptance_sha256")!=criteria.get(item["story_id"]):
            raise ValueError("Acceptance criteria fingerprint changed")
        if item["status"] not in {"PARTIAL","NOT_STARTED","BLOCKED","IN_REVIEW","DONE"}:raise ValueError("Invalid story status")
        if item["status"]=="DONE":
            from .inventory_completion import KIND,verify as verify_inventory
            if item["story_id"]=="US-001" and isinstance(item.get("completion_evidence"),dict) and item["completion_evidence"].get("kind")==KIND:
                administrative.append(verify_inventory(item,inventory,root))
            elif item["story_id"]=="US-002":
                from .schema_completion import KIND as SCHEMA_KIND,verify as verify_catalog
                if isinstance(item.get("completion_evidence"),dict) and item["completion_evidence"].get("kind")==SCHEMA_KIND:
                    administrative.append(verify_catalog(item,inventory,root))
                else:
                    if not reviewer_keys or not as_of or not item.get("completion_envelope"):raise ValueError("DONE requires independently signed completion evidence")
                    _completion(item,reviewer_keys,as_of)
            else:
                if not reviewer_keys or not as_of or not item.get("completion_envelope"):raise ValueError("DONE requires independently signed completion evidence")
                _completion(item,reviewer_keys,as_of)
        if not item["remaining"].strip():raise ValueError("Missing acceptance limitations")
        for module in item["modules"]:
            path=(root/module["path"]).resolve()
            if root.resolve() not in path.parents or sha256(path.read_bytes()).hexdigest()!=module["sha256"]:
                raise ValueError("Missing or altered implementation evidence")
    return {"stories":51,"done":sum(x["status"]=="DONE" for x in stories),
            "counts":{s:sum(x["status"]==s for x in stories) for s in ("IN_REVIEW","PARTIAL","NOT_STARTED","BLOCKED","DONE")},
            "independent_validation":"SIGNED_RESEARCH_ACCEPTANCE_REQUIRED_OBJECTIVE_INVENTORY_AND_CATALOG",
            "objective_software_acceptance":administrative}


if __name__=="__main__":
    print(json.dumps(audit(),sort_keys=True))
