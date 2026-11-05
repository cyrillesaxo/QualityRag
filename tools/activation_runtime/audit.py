"""Coverage audit: objective inventory/catalog evidence, independent signed research acceptance."""
from hashlib import sha256
import json
from pathlib import Path
import re
from .common import fingerprint,HEX


REPO="cyrillesaxo/QualityRag"
TRUST_SCHEMA="qualityrag.reviewer-trust/v1"
TRUST_STATUSES={"active","retired","compromised"}


def load_trust(path):
    """Reviewer trust store: key ID -> entry with an Ed25519 public key and a validity window.

    Completion receipts are historical records, so a receipt stays valid after its key is
    rotated out ("retired", only for receipts issued before retired_at). A "compromised" key
    invalidates every receipt it ever signed.
    """
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from .common import strict_json
    data=strict_json(Path(path).read_bytes(),max_bytes=1_000_000)
    if not isinstance(data,dict) or data.get("schema")!=TRUST_SCHEMA or not isinstance(data.get("reviewers"),list):
        raise ValueError("Invalid reviewer trust store")
    trust={}
    for entry in data["reviewers"]:
        if not isinstance(entry,dict):raise ValueError("Invalid reviewer entry")
        kid=entry.get("key_id")
        if not isinstance(kid,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}",kid) or kid in trust:
            raise ValueError("Invalid or duplicate reviewer key ID")
        login=entry.get("github_login")
        if not isinstance(login,str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}",login):
            raise ValueError("Reviewer GitHub login required for the independence check")
        status=entry.get("status")
        if status not in TRUST_STATUSES or (status=="retired")!=("retired_at" in entry):
            raise ValueError("Reviewer status must be active, retired (with retired_at) or compromised")
        valid_from=_instant(entry.get("valid_from"))
        retired_at=_instant(entry["retired_at"]) if status=="retired" else None
        if retired_at is not None and retired_at<=valid_from:raise ValueError("Reviewer window is empty")
        trust[kid]={"key":Ed25519PublicKey.from_public_bytes(base64.b64decode(entry.get("public_key",""),validate=True)),
                    "github_login":login.lower(),"status":status,"valid_from":valid_from,"retired_at":retired_at}
    return trust


def _instant(value):
    from datetime import datetime
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",value):
        raise ValueError("UTC timestamp YYYY-MM-DDTHH:MM:SSZ required")
    return datetime.fromisoformat(value.replace("Z","+00:00"))


def _completion(item,trust,as_of,fetch):
    """Verify a signed completion receipt as a historical record.

    The issue time is self-declared, so it is bounded by evidence the reviewer cannot set:
    it must not precede the referenced CI run's completion on GitHub nor the key's validity
    start, must precede retirement of a rotated key, and must not be in the future. The
    implementation must be contained in the merge commit, the merge commit in main, and the
    reviewer must not be the implementation commit's author.
    """
    from .authority import ATTEST_SCHEMA,verify,_validate_period
    envelope=item.get("completion_envelope")
    kid=envelope.get("key_id") if isinstance(envelope,dict) else None
    entry=trust.get(kid) if isinstance(kid,str) else None
    if entry is None:raise ValueError("Completion signed by an untrusted reviewer key")
    if entry["status"]=="compromised":raise ValueError("Completion signed by a compromised reviewer key")
    body=verify(envelope,{kid:entry["key"]},schema=ATTEST_SCHEMA)
    if set(body)!={"completion","issued_at","expires_at"}:raise ValueError("Wrong completion purpose")
    issued=_instant(body["issued_at"])
    _validate_period(body["issued_at"],body["expires_at"],body["issued_at"])
    if issued>_instant(as_of):raise ValueError("Completion issued in the future")
    if issued<entry["valid_from"]:raise ValueError("Completion predates the reviewer key")
    if entry["retired_at"] is not None and issued>=entry["retired_at"]:
        raise ValueError("Completion issued after the reviewer key was retired")
    receipt=body["completion"]
    commit=item.get("implementation_commit")
    if not isinstance(commit,str) or not re.fullmatch("[0-9a-f]{40}",commit):
        raise ValueError("Exact implementation commit required")
    expected={"schema":"qualityrag.story-completion/v1","story_id":item["story_id"],
              "implementation_commit":commit,
              "module_inventory_sha256":fingerprint(item["modules"]),
              "acceptance_sha256":item["acceptance_sha256"]}
    if not isinstance(receipt,dict) or any(receipt.get(k)!=v for k,v in expected.items()):
        raise ValueError("Completion source or criteria mismatch")
    merge=receipt.get("merge_commit","")
    if not isinstance(merge,str) or not re.fullmatch("[0-9a-f]{40}",merge):raise ValueError("Merged review evidence required")
    ci=receipt.get("ci",{})
    match=re.fullmatch(r"https://github\.com/"+re.escape(REPO)+r"/actions/runs/([1-9][0-9]{0,18})",str(ci.get("url","")))
    if (not isinstance(ci,dict) or ci.get("status")!="PASSED" or ci.get("commit")!=commit
            or not HEX.fullmatch(str(ci.get("receipt_sha256",""))) or not match):
        raise ValueError("Passing commit-bound CI evidence required")
    if receipt.get("all_acceptance_criteria")!="MET":raise ValueError("Independent acceptance is incomplete")
    run=fetch("/actions/runs/"+match.group(1))
    if (run.get("head_sha")!=commit or run.get("status")!="completed" or run.get("conclusion")!="success"
            or run.get("repository",{}).get("full_name")!=REPO):
        raise ValueError("Referenced CI run did not pass on the implementation commit")
    if issued<_instant(str(run.get("updated_at",""))):raise ValueError("Completion predates its CI evidence")
    if fetch("/compare/"+commit+"..."+merge).get("status") not in ("ahead","identical"):
        raise ValueError("Merge commit does not contain the implementation")
    if fetch("/compare/"+merge+"...main").get("status") not in ("ahead","identical"):
        raise ValueError("Merge commit is not on main")
    author=(fetch("/commits/"+commit).get("author") or {}).get("login","")
    if not author or author.lower()==entry["github_login"]:
        raise ValueError("Reviewer must be independent of the implementation author")
    return {"story_id":item["story_id"],"reviewer_key":kid,"issued_at":body["issued_at"],"ci_run":int(match.group(1))}


def audit(root=None,*,trust=None,as_of=None,_fetch=None):
    """Audit the inventory. DONE stories beyond US-001/002 need a receipt signed by a key in the
    reviewer trust store (loaded from the repository unless ``trust`` is given)."""
    from datetime import datetime,timezone
    root=Path(__file__).resolve().parents[2] if root is None else Path(root)
    if trust is None:
        store=root/"tools/activation_runtime/reviewer-trust.json"
        trust=load_trust(store) if store.exists() else {}  # no store: no reviewer can complete a story
    if as_of is None:as_of=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if _fetch is None:
        from .inventory_completion import github as _fetch
    inventory=json.loads((root/"tools/activation_runtime/capabilities.json").read_text())
    stories=inventory["stories"];wanted={"US-"+str(n).zfill(3) for n in range(1,52)}
    actual=[x["story_id"] for x in stories]
    if len(actual)!=51 or len(set(actual))!=51 or set(actual)!=wanted:raise ValueError("Missing or duplicate story coverage")
    content=(root/"FR.MD").read_text()
    declared=set("US-"+x for x in re.findall(r"\*\*US-(\d{3}) ·",content))
    if declared!=wanted:raise ValueError("Inventory differs from FR.MD")
    criteria={"US-"+number:sha256(text.strip().encode()).hexdigest() for number,text in re.findall(
        r"\*\*US-(\d{3}) ·[^\n]+\n.*?\*\*Acceptance:\*\* ([^\n]+)",content,re.S)}
    administrative=[];signed=[]
    for item in stories:
        if item.get("acceptance_sha256")!=criteria.get(item["story_id"]):
            raise ValueError("Acceptance criteria fingerprint changed")
        if item["status"] not in {"PARTIAL","NOT_STARTED","BLOCKED","IN_REVIEW","DONE"}:raise ValueError("Invalid story status")
        if item["status"]=="DONE":
            from .inventory_completion import KIND,verify as verify_inventory
            if item["story_id"]=="US-001" and isinstance(item.get("completion_evidence"),dict) and item["completion_evidence"].get("kind")==KIND:
                administrative.append(verify_inventory(item,inventory,root,_fetch=_fetch))
            elif item["story_id"]=="US-002":
                from .schema_completion import KIND as SCHEMA_KIND,verify as verify_catalog
                if isinstance(item.get("completion_evidence"),dict) and item["completion_evidence"].get("kind")==SCHEMA_KIND:
                    administrative.append(verify_catalog(item,inventory,root,_fetch=_fetch))
                else:
                    if not item.get("completion_envelope"):raise ValueError("DONE requires independently signed completion evidence")
                    signed.append(_completion(item,trust,as_of,_fetch))
            else:
                if not item.get("completion_envelope"):raise ValueError("DONE requires independently signed completion evidence")
                signed.append(_completion(item,trust,as_of,_fetch))
        if not item["remaining"].strip():raise ValueError("Missing acceptance limitations")
        for module in item["modules"]:
            path=(root/module["path"]).resolve()
            if root.resolve() not in path.parents or sha256(path.read_bytes()).hexdigest()!=module["sha256"]:
                raise ValueError("Missing or altered implementation evidence")
    return {"stories":51,"done":sum(x["status"]=="DONE" for x in stories),
            "counts":{s:sum(x["status"]==s for x in stories) for s in ("IN_REVIEW","PARTIAL","NOT_STARTED","BLOCKED","DONE")},
            "independent_validation":"SIGNED_RESEARCH_ACCEPTANCE_REQUIRED_OBJECTIVE_INVENTORY_AND_CATALOG",
            "objective_software_acceptance":administrative,"signed_completions":signed,
            "trusted_reviewer_keys":sorted(k for k,v in trust.items() if v["status"]!="compromised")}


if __name__=="__main__":
    print(json.dumps(audit(),sort_keys=True))
