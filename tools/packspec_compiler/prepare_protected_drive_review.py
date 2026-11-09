"""Prepare and separately sign a customer-reviewed protected Drive assertion.

The source custodian and meaning reviewer should inspect the *same* prepared
payload independently and sign with different offline private keys. This
helper does not automatically decide that a statement is true.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign,canonical,ATTEST_SCHEMA

SOURCE=re.compile(r"^google_drive/[a-f0-9]{32}$")
HEX=re.compile(r"^[a-f0-9]{64}$")
ID=re.compile(r"^[A-Za-z0-9._-]{1,128}$")
ORIGIN=re.compile(r"^org_[a-f0-9]{24,64}$")


def required(ok, reason):
    if not ok:raise ValueError(reason)


def read_json(path):
    raw=Path(path).read_bytes()
    required(0<len(raw)<100_000,"INPUT_SIZE_OUT_OF_BOUNDS")
    def pairs(items):
        result={}
        for k,v in items:
            required(k not in result,"DUPLICATE_JSON_KEY")
            result[k]=v
        return result
    return json.loads(raw.decode("utf8","strict"),object_pairs_hook=pairs)


def write_new(file,object_):
    path=Path(file)
    required(not path.exists() and not path.is_symlink(),"OUTPUT_EXISTS")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf8") as out:
            json.dump(object_,out,ensure_ascii=False,indent=2)
            out.write("\n")
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def prepare(args):
    for label,value in {
        "service":args.service,"environment":args.environment,
        "policy_sha":args.policy_sha,"owner_subject":args.owner_subject,
        "folder_id":args.folder_id,"source_id":args.source_id,
        "requirement_id":args.requirement_id,"origin":args.origin
    }.items():
        required(isinstance(value,str) and value and value.isascii(),
                 "INVALID_"+label.upper())
    required(ID.fullmatch(args.service) and ID.fullmatch(args.environment) and
             HEX.fullmatch(args.policy_sha) and ID.fullmatch(args.folder_id) and
             SOURCE.fullmatch(args.source_id) and ID.fullmatch(args.requirement_id) and
             ORIGIN.fullmatch(args.origin),"INVALID_REVIEW_SCOPE")
    data=Path(args.source).read_bytes()
    required(0<len(data)<=96_000,"SOURCE_FILE_SIZE_OUT_OF_BOUNDS")
    lines=data.decode("utf8","strict").replace("\r\n","\n").replace("\r","\n").split("\n")
    required(1<=args.line_number<=len(lines),"INVALID_LINE_ANCHOR")
    witness={
        "sourceId":args.source_id,"revision":sha256(data).hexdigest(),
        "requirementId":args.requirement_id,"lineNumber":args.line_number,
        "lineSha256":sha256(lines[args.line_number-1].encode("utf8")).hexdigest(),
        "origin":args.origin,"status":args.status
    }
    return assemble_payload(args,[witness])


def assemble_payload(args,witnesses):
    now=datetime.now(timezone.utc)
    expires=now+timedelta(minutes=5)
    payload={
        "service":args.service,"environment":args.environment,
        "policy_signature":"UNSIGNED-V0.1-PACK-SHA256:"+args.policy_sha,
        "nonce":"nonce-"+secrets.token_hex(16),
        "issued_at":now.isoformat(timespec="milliseconds").replace("+00:00","Z"),
        "expires_at":expires.isoformat(timespec="milliseconds").replace("+00:00","Z"),
        "witnesses":witnesses,
        "observations":{
            "kind":"qualityrag.protected-drive-human-review/v1",
            "owner_binding":sha256(("qualityrag.review-owner/v1:"+
                                    args.owner_subject).encode("utf8")).hexdigest(),
            "folder_id":args.folder_id,
            "review_basis":"HUMAN_SEMANTIC_APPROVAL",
            "origin_basis":"CUSTODIAN_ATTESTED"
        }
    }
    canonical(payload)
    write_new(args.out,payload)
    return {"prepared":True,"out":args.out,"witnessCount":len(witnesses),
            "validityMinutes":5,
            "note":"Independent custodians and meaning reviewers must inspect every source line and its governing PackSpec obligation before signing."}


def prepare_manifest(args):
    # Multi-clause remediation is explicitly reviewed. There is no automatic
    # SUPPORTS default: every manifest entry must specify its reviewed status.
    required(ID.fullmatch(args.service) and ID.fullmatch(args.environment) and
             HEX.fullmatch(args.policy_sha) and ID.fullmatch(args.folder_id) and
             isinstance(args.owner_subject,str) and
             bool(args.owner_subject) and args.owner_subject.isascii(),
             "INVALID_REVIEW_SCOPE")
    manifest=read_json(args.manifest)
    required(isinstance(manifest,dict) and set(manifest)=={"witnesses"} and
             isinstance(manifest["witnesses"],list) and
             1<=len(manifest["witnesses"])<=8,"INVALID_WITNESS_MANIFEST")
    witnesses=[]
    identities=set()
    for item in manifest["witnesses"]:
        required(isinstance(item,dict) and set(item)=={
            "sourceId","requirementId","origin","status",
            "lineNumber","sourcePath"
        },"INVALID_WITNESS_MANIFEST_ROW")
        required(isinstance(item["sourceId"],str) and
                 SOURCE.fullmatch(item["sourceId"]) and
                 isinstance(item["requirementId"],str) and
                 ID.fullmatch(item["requirementId"]) and
                 isinstance(item["origin"],str) and ORIGIN.fullmatch(item["origin"]) and
                 item["status"] in ("SUPPORTS","CONTRADICTS","UNKNOWN") and
                 type(item["lineNumber"]) is int and
                 1<=item["lineNumber"]<=6000 and
                 isinstance(item["sourcePath"],str) and
                 item["sourcePath"],"INVALID_WITNESS_MANIFEST_ROW")
        identity=(item["sourceId"],item["requirementId"],item["lineNumber"])
        required(identity not in identities,"DUPLICATE_REVIEW_WITNESS")
        identities.add(identity)
        source_file=Path(item["sourcePath"])
        required(source_file.is_file() and not source_file.is_symlink(),
                 "INVALID_REVIEW_SOURCE_FILE")
        data=source_file.read_bytes()
        required(0<len(data)<=96_000,"SOURCE_FILE_SIZE_OUT_OF_BOUNDS")
        lines=data.decode("utf8","strict").replace("\r\n","\n").replace("\r","\n").split("\n")
        required(len(lines)<=6000 and all(len(x)<=1200 for x in lines),
                 "SOURCE_FILE_NOT_FULLY_INDEXABLE")
        required(item["lineNumber"]<=len(lines),"INVALID_LINE_ANCHOR")
        witnesses.append({
            "sourceId":item["sourceId"],"revision":sha256(data).hexdigest(),
            "requirementId":item["requirementId"],
            "lineNumber":item["lineNumber"],
            "lineSha256":sha256(lines[item["lineNumber"]-1].encode("utf8")).hexdigest(),
            "origin":item["origin"],"status":item["status"]
        })
    return assemble_payload(args,witnesses)


def sign_review(args):
    required(args.attest_reviewed,"EXPLICIT_REVIEW_CONFIRMATION_REQUIRED")
    p=Path(args.private_key)
    required(p.is_file() and not p.is_symlink(),"INVALID_PRIVATE_KEY_FILE")
    if os.name=="posix":
        required(stat.S_IMODE(p.stat().st_mode)&0o077==0,
                 "INSECURE_PRIVATE_KEY_PERMISSIONS")
    key=serialization.load_pem_private_key(p.read_bytes(),password=None)
    required(isinstance(key,Ed25519PrivateKey),"ED25519_PRIVATE_KEY_REQUIRED")
    required(ID.fullmatch(args.key_id),"INVALID_REVIEW_KEY_ID")
    payload=read_json(args.payload)
    required(isinstance(payload,dict) and
             set(payload)=={"service","environment","policy_signature","nonce",
                            "issued_at","expires_at","witnesses","observations"},
             "INVALID_PREPARED_REVIEW")
    # Signing does not establish truth. The server will check authorized role,
    # current owner settings, exact provider bytes and policy mapping.
    signed=sign(payload,key,key_id=args.key_id,schema=ATTEST_SCHEMA)
    write_new(args.out,signed)
    return {"signed":True,"role":args.role,"out":args.out,
            "caution":"Signature proves the review key approved a claim, not external source truth."}


def build_request(args):
    custody=read_json(args.custody)
    meaning=read_json(args.meaning)
    required(isinstance(custody,dict) and isinstance(meaning,dict) and
             canonical(custody["payload"])==canonical(meaning["payload"]),
             "REVIEWER_PAYLOADS_DISAGREE")
    payload=custody["payload"]
    required(ID.fullmatch(args.request_id) and ID.fullmatch(args.trace_id),
             "INVALID_REQUEST_ID")
    write_new(args.out,{
        "serviceId":payload["service"],"environment":payload["environment"],
        "requestId":args.request_id,"traceId":args.trace_id,
        "custody":custody,"meaning":meaning
    })
    return {"requestCreated":True,"out":args.out,
            "caution":"Do not send a protected request until the two independent reviewers approve."}


def main(argv=None):
    parser=argparse.ArgumentParser(description="Customer-controlled protected Drive review signer")
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("prepare")
    for field in ("service","environment","policy-sha","owner-subject","folder-id",
                  "source-id","requirement-id","origin","source","out"):
        p.add_argument("--"+field,required=True)
    p.add_argument("--line-number",type=int,default=1)
    p.add_argument("--status",choices=("SUPPORTS","CONTRADICTS","UNKNOWN"),default="UNKNOWN")
    p_multi=sub.add_parser("prepare-manifest")
    for field in ("service","environment","policy-sha","owner-subject","folder-id",
                  "manifest","out"):
        p_multi.add_argument("--"+field,required=True)
    sign_parser=sub.add_parser("sign")
    for field in ("payload","private-key","key-id","out"):
        sign_parser.add_argument("--"+field,required=True)
    sign_parser.add_argument("--role",required=True,choices=("custodian","meaningReviewer"))
    sign_parser.add_argument("--attest-reviewed",action="store_true")
    combine=sub.add_parser("build-request")
    for field in ("custody","meaning","request-id","trace-id","out"):
        combine.add_argument("--"+field,required=True)
    args=parser.parse_args(argv)
    try:
        result={"prepare":prepare,"prepare-manifest":prepare_manifest,
                "sign":sign_review,
                "build-request":build_request}[args.command](args)
        print(json.dumps(result,indent=2))
        return 0
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print(json.dumps({"ok":False,"reason":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
