#!/usr/bin/env python3
"""Executable contrast: metadata replay alone vs customer-signed source custody.

No customer documents or real identities. A real local registry HTTP demo
produces the receipt. A demo-only custodian key signs exact synthetic bytes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1]
for item in (ROOT/"tools"/"packspec_compiler", ROOT/"sdk"/"python"):
    if str(item) not in sys.path:
        sys.path.insert(0,str(item))

from studio_custody import SCHEMA, CustodyError, sign_customer_manifest, verify_customer_manifest
from qualityrag.verify_receipt import verify_package, _hash
from qualityrag import evaluate

def token(prefix, n):
    return f"{prefix}_{n:032x}"

def main():
    with tempfile.TemporaryDirectory(prefix="qualityrag-custody-demo-") as d:
        directory=Path(d)
        exported=directory/"original.json"
        result=subprocess.run(["node", str(ROOT/"scripts"/"evidence-assurance-show-me.mjs"),
                               "--export",str(exported)],
                cwd=ROOT,timeout=20,capture_output=True,text=True,check=True)
        receipt=json.loads(exported.read_text(encoding="utf-8"))
        before=verify_package(receipt)
        assert before["verdict"]=="INCONCLUSIVE"

        # Customer-controlled manifest is prepared from *separate* synthetic files.
        # In a real review, a customer custodian must verify source ownership and
        # approve the provenance mapping independently of the RAG output.
        source_files={}
        records=[]
        for n in range(1,4):
            ref=token("src",n)
            file=directory/f"customer-source-{n}.bin"
            file.write_bytes(f"Synthetic source snapshot {n}: shared original policy.\n".encode())
            source_files[ref]=str(file)
            data=file.read_bytes()
            records.append({
                "source_ref":ref,"declared_origin":token("org",1),
                "content_sha256":sha256(data).hexdigest(),"content_length":len(data)
            })
        payload=receipt["payload"]
        manifest={
            "schema":SCHEMA,"evaluationId":payload["evaluationId"],
            "serviceId":payload["serviceId"],"environment":payload["environment"],
            "policySha256":payload["policySha256"],"sources":records
        }
        custodian=Ed25519PrivateKey.generate()
        signed=sign_customer_manifest(
            receipt=receipt,manifest=manifest,source_files=source_files,
            private_key=custodian,key_id="DEMO_NOT_PRODUCTION_CUSTOMER_KEY",
            nonce="custody-demo-1")
        checked=verify_customer_manifest(
            receipt=receipt,signed_custody=signed,
            public_key=custodian.public_key(),source_files=source_files)
        assert checked["sourceCustodyVerified"] and checked["custodySourceCount"]==3

        # A dishonest telemetry producer can invent a second origin label.
        # It then recalculates both its expected verdict and unsigned digest.
        # The independent metadata replay correctly reproduces the tampered
        # *declaration* but cannot know that the origin claim is fabricated.
        forged=json.loads(json.dumps(receipt))
        forged["payload"]["evidence"][-1]["origin"]=token("org",2)
        forged["payload"]["expectedResult"]=evaluate(
            forged["payload"]["policy"],forged["payload"]["evidence"],
            as_of=forged["payload"]["asOf"])
        forged["integrity"]["sha256"]=_hash(forged["payload"])
        base=verify_package(forged)
        assert base["verified"] and base["verdict"]=="ADMIT"
        blocked=False
        reason=""
        try:
            verify_customer_manifest(
                receipt=forged,signed_custody=signed,
                public_key=custodian.public_key(),source_files=source_files)
        except CustodyError as exc:
            blocked=True
            reason=str(exc)
        assert blocked and reason=="DECLARED_ORIGIN_MISMATCH"
        print(json.dumps({
            "demonstration":"SYNTHETIC REAL-JS-REGISTRY-EXPORT + PYTHON-CUSTOMER-CUSTODY",
            "unmodifiedReceipt":{"verdict":before["verdict"],"sourceCount":3,
                                  "declaredOrigins":1,"custodySignatureAndBytesVerified":True},
            "forgedOriginReceipt":{"unsignedReplay":base["verdict"],
                                   "unsignedReplayAccepted":True,
                                   "customerCustodyAccepted":False,
                                   "rejectionReason":reason},
            "securityBoundary":"Customer-controlled signed claim and exact supplied bytes",
            "notEstablished":["original publisher authenticity","real-world origin independence",
                              "evidence semantic truth","policy completeness",
                              "regulatory compliance","production key custody"],
        },indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
