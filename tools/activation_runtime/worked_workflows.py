"""Runnable reviewed-activation examples; generated keys are authored test authority only."""
import argparse
import base64
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .authority import issue_access,review_binding
from .artifacts import make_manifest,sign_manifest
from .common import canonical,fingerprint
from .pipeline import encode
from .profile_fixtures import generate
from .service import Application

AT="2026-11-04T12:00:00Z"
PERIOD={"issued_at":"2026-11-04T00:00:00Z","expires_at":"2026-11-05T00:00:00Z"}


def run(output):
    root=Path(output);root.mkdir(parents=True,exist_ok=False)
    profiles=generate(root/"profiles")
    issuer,release,author,reviewer=[Ed25519PrivateKey.generate() for _ in range(4)]
    authorities={"research":{"authors":{"fixture-author":author.public_key()},"review":{"example-reviewer":reviewer.public_key()},
                             "subjects":{"example-reviewer":"independent-review-required"}}}
    app=Application(root/"runtime",access_keys={"example-issuer":issuer.public_key()},release_keys={"example-release":release.public_key()},
        clock=lambda:AT,preservation_authorities=authorities)
    token=issue_access(subject="example-reader",tenant="research",scopes=["read","write"],key=issuer,key_id="example-issuer",**PERIOD)
    authorization="Bearer "+base64.urlsafe_b64encode(canonical(token)).decode().rstrip("=")
    cases=[]
    changes={"clinical-description":{"diagnosis":"asthma"},"nursing":{"instruction":"The exam asks which action is permitted.","unit":"g"},
             "legal":{"actor":"bob","recipient":"alice","polarity":"POSITIVE"},"education":{"exception":"A"}}
    upload=lambda raw:app.dispatch("source",{"base64":base64.b64encode(raw).decode()},authorization)["source_sha256"]
    for domain,mutation in changes.items():
        profile=profiles[domain];values=profile["source"];ir=profile["ir"];contract=profile["contract"]
        raw=canonical(values);source=upload(raw)
        mapping={field:"field-"+str(i) for i,field in enumerate(values)}
        context={"purpose":"PRESERVATION_CONTRACT_REVIEW","source_sha256":source,"policy_ir_sha256":ir["ir_sha256"],
                 "policy_source_sha256":ir["source"]["sha256"],"contract_sha256":fingerprint(contract)}
        directory=root/"cases"/domain;directory.mkdir(parents=True)
        for variant in ("preserved","refused","fallback"):
            artifact=encode(raw,mapping)
            if variant!="preserved":
                for field,value in mutation.items():artifact["payload"][mapping[field]]=value
            address=upload(canonical(artifact))
            manifest=make_manifest(tenant="research",source_sha256=source,artifact_sha256=address,policy_ir_sha256=ir["ir_sha256"],sequence=1)
            signed=sign_manifest(manifest,release,key_id="example-release",**PERIOD)
            review=review_binding(context,decision="APPROVE",reviewer="independent-review-required",author_key_id="fixture-author",
                key=reviewer,key_id="example-reviewer",nonce=domain+"-"+variant,**PERIOD)
            request={"source_sha256":source,"artifact":artifact,"signed_manifest":signed,"policy_ir":ir,"contract":contract,
                     "signed_review":review,"allow_fallback":variant=="fallback"}
            result=app.dispatch("activate-plan",request,authorization)
            expected={"preserved":"REQUIRES_REVIEW","refused":"REFUSE","fallback":"FALLBACK"}[variant]
            if result["action"]!=expected or result["can_generate"]:raise ValueError("Worked workflow outcome mismatch")
            if variant=="refused" and result["output"] is not None:raise ValueError("Rejected output was released")
            if variant!="refused" and result["output"]!=values:raise ValueError("Original distinctions changed")
            (directory/(variant+"-request.json")).write_bytes(canonical(request))
            (directory/(variant+"-receipt.json")).write_bytes(canonical(result))
            cases.append({"domain":domain,"variant":variant,"action":result["action"],"source_sha256":source,
                          "policy_ir_sha256":ir["ir_sha256"],"receipt":"cases/"+domain+"/"+variant+"-receipt.json",
                          "receipt_sha256":fingerprint(result)})
    report={"schema":"qualityrag.reviewed-workflows/v1","scope":"AUTHORED_ENGINEERING_EXAMPLES_NOT_INDEPENDENT_DOMAIN_REVIEW",
        "cases":cases,"domains":4,"scenario_count":12,"can_generate":False,"independent_domain_acceptance":"NOT_ESTABLISHED",
        "ephemeral_authority":"Generated keys test signature paths; no external reviewer identity is claimed",
        "real_video":"Run tools.activation_runtime.run_research separately; no video advantage is claimed"}
    (root/"receipt.json").write_bytes(canonical(report))
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",required=True);args=parser.parse_args()
    result=run(args.out)
    print(json.dumps({"domains":result["domains"],"scenarios":result["scenario_count"],"receipt":str(Path(args.out)/"receipt.json"),"can_generate":False}))


if __name__=="__main__":main()
