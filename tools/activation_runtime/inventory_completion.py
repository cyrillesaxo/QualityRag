"""Objective US-001 source/CI acceptance; never substitutes for domain review."""
from hashlib import sha1,sha256
import json
import os
from pathlib import Path
import re
from urllib.request import Request,HTTPRedirectHandler,build_opener
from .common import fingerprint,HEX

REPO="cyrillesaxo/QualityRag"
WORKFLOW=".github/workflows/activation-runtime.yml"
KIND="GITHUB_VERIFIED_SOURCE_INVENTORY/v1"
REQUIRED_STEPS={"Run npm ci && npm test",
    "Run python -m unittest discover -s tools/packspec_compiler -p 'test_finite_activation.py' -v",
    "Run python -m unittest discover -s tools/activation_runtime/tests -p 'test_*.py' -v",
    "Run python -m unittest discover -s tools/packspec_compiler/tests -p 'test_*.py' -v",
    "Run python -m unittest discover -s tools/research_ledger/tests -p 'test_*.py' -v",
    "Run python -m tools.activation_runtime.audit"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):raise ValueError("Acceptance source redirect refused")


def github(path):
    headers={"Accept":"application/vnd.github+json","User-Agent":"QualityRag-source-inventory"}
    token=os.environ.get("GITHUB_TOKEN")
    if token:headers["Authorization"]="Bearer "+token
    request=Request("https://api.github.com/repos/"+REPO+path,headers=headers)
    try:
        with build_opener(NoRedirect()).open(request,timeout=10) as response:
            raw=response.read(4_000_001)
        if len(raw)>4_000_000:raise ValueError("Acceptance source response budget")
        from .common import strict_json
        return strict_json(raw,max_bytes=4_000_000)
    except (OSError,ValueError) as exc:
        raise ValueError("Live GitHub acceptance evidence unavailable; completion cannot be verified") from exc


def verify(item,inventory,root,*,_fetch=None):
    """Use live HTTPS GitHub metadata by default. _fetch supplies isolated test fixtures."""
    proof=item.get("completion_evidence")
    if item.get("story_id")!="US-001" or not isinstance(proof,dict) or set(proof)!={"kind","repository","implementation_commit","module_inventory_sha256","acceptance_sha256","workflow_run_id","url"}:
        raise ValueError("Only US-001 source inventory has objective software acceptance")
    commit=proof["implementation_commit"];run_id=proof["workflow_run_id"]
    if (proof["kind"]!=KIND or proof["repository"]!=REPO or not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit)
        or item.get("implementation_commit")!=commit or type(run_id) is not int or not 1<=run_id<2**63
        or proof["url"]!="https://github.com/"+REPO+"/actions/runs/"+str(run_id)
        or proof["acceptance_sha256"]!=item["acceptance_sha256"] or proof["module_inventory_sha256"]!=fingerprint(item["modules"])):
        raise ValueError("Inventory acceptance scope mismatch")
    if [c.get("number") for c in item["criteria"]]!=[1,2,3,4] or any(c.get("acceptance")!="MET_OBSERVED_SOURCE_AND_CI" for c in item["criteria"]):
        raise ValueError("Every US-001 criterion needs recorded objective acceptance")
    for story in inventory["stories"]:
        if (not isinstance(story.get("branch"),str) or not story["branch"] or not story.get("test_or_receipt") or not story.get("remaining")
            or not isinstance(story.get("base_commit"),str) or not re.fullmatch('[0-9a-f]{40}',story["base_commit"])):
            raise ValueError("Incomplete claimed implementation inventory")
    if inventory.get("implementation_boundaries")!={"canonical_ff_rct_decoder":"UNAVAILABLE","independent_domain_admission":"NOT_ESTABLISHED","reference_scene_decoder":"AVAILABLE_RESEARCH_REFERENCE"}:
        raise ValueError("Explicit decoder and admission boundaries required")
    # Pin the inventory implementation, not future unrelated research changes.
    root=Path(root).resolve();local={}
    for module in [*item["modules"],{"path":WORKFLOW}]:
        path=module["path"];target=(root/path).resolve()
        if root not in target.parents:raise ValueError("Inventory source escapes repository")
        try:raw=target.read_bytes()
        except OSError as exc:raise ValueError("Inventory implementation source unavailable") from exc
        if "sha256" in module and sha256(raw).hexdigest()!=module["sha256"]:raise ValueError("Inventory implementation differs from accepted source")
        local[path]=sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    fetch=github if _fetch is None else _fetch
    run=fetch('/actions/runs/'+str(run_id))
    if (run.get("head_sha")!=commit or run.get("status")!="completed" or run.get("conclusion")!="success"
        or run.get("event")!="push" or run.get("path")!=WORKFLOW
        or run.get("repository",{}).get("full_name")!=REPO or run.get("head_repository",{}).get("full_name")!=REPO):
        raise ValueError("Actual CI source, result or workflow mismatch")
    jobs=fetch('/actions/runs/'+str(run_id)+'/jobs?per_page=100').get("jobs",[])
    matched=[j for j in jobs if j.get("name")=="bounded-activation"]
    if len(matched)!=1 or matched[0].get("conclusion")!="success":raise ValueError("Required CI job unavailable")
    steps=matched[0].get("steps",[])
    if not REQUIRED_STEPS.issubset({s.get("name") for s in steps}) or any(s.get("conclusion")!="success" for s in steps):
        raise ValueError("Required tests/audit skipped, missing or failed")
    tree=fetch('/git/trees/'+commit+'?recursive=1')
    if tree.get("truncated"):raise ValueError("Incomplete immutable source tree")
    objects={row["path"]:row["sha"] for row in tree.get("tree",[]) if row.get("type")=="blob"}
    if any(objects.get(path)!=address for path,address in local.items()):raise ValueError("CI did not test the recorded inventory implementation")
    baseline=fetch('/pulls/69')
    if type(baseline.get("merged")) is not bool:raise ValueError("PR #69 state unavailable")
    if not baseline["merged"] and any(s["story_id"]=="US-022" and s["status"]=="DONE" for s in inventory["stories"]):
        raise ValueError("Open PR #69 cannot satisfy its merge prerequisite")
    return {"story_id":"US-001","scope":"SOURCE_INVENTORY_SOFTWARE_ONLY","ci_run_id":run_id,"implementation_commit":commit,
            "pr_69":"MERGED" if baseline["merged"] else "IN_REVIEW","independent_domain_validation":"NOT_ESTABLISHED"}
