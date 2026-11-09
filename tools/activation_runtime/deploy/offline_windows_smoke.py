#!/usr/bin/env python3
"""Offline Windows operator smoke: real signed access through an SSH tunnel.

This script sends the ephemeral *signed token*, never the private key.
Tunnel PuTTY local 18769 -> remote 127.0.0.1:8769.
The public Caddy /api/* route must remain 503 during this test.
"""
import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DOMAIN = b"QUALITYRAG/qualityrag.signed-observations/v1\x00"
ENDPOINT = "http://127.0.0.1:18769"
KEY_ID = "production-access-1"

def signed_bearer(raw_key: bytes):
    if len(raw_key) != 32:
        raise ValueError("Expected exactly 32 bytes of raw Ed25519 private key")
    now = datetime.now(timezone.utc)
    stamp = lambda dt: dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = {
        "access": {"subject": "netlify-gateway", "tenant": "dodo-operations", "scopes": ["read"]},
        "issued_at": stamp(now - timedelta(seconds=5)),
        "expires_at": stamp(now + timedelta(minutes=5)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    signature = Ed25519PrivateKey.from_private_bytes(raw_key).sign(DOMAIN + canonical)
    envelope = {
        "schema": "qualityrag.signed-observations/v1",
        "canonical": "QR-CJSON-1",
        "key_id": KEY_ID,
        "payload": payload,
        "signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode(),
    }
    return "Bearer " + base64.urlsafe_b64encode(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()

def call(route, body, bearer=None):
    headers={"Content-Type":"application/json"}
    if bearer is not None: headers["Authorization"]=bearer
    req=Request(ENDPOINT+"/api/"+route,
        data=json.dumps(body,separators=(",", ":")).encode(),
        headers=headers,method="POST")
    try:
        with urlopen(req,timeout=10) as response:
            return response.status,json.loads(response.read(524288))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read(4096))

def main():
    if sys.platform != "win32":
        raise RuntimeError("Run this smoke test on Windows over PuTTY SSH tunnel")
    if len(sys.argv)!=2:
        raise SystemExit("Usage: py offline_windows_smoke.py %USERPROFILE%\\QualityRAG-keys\\production-access-1.key")
    private=Path(sys.argv[1]).resolve()
    if private.is_symlink() or not private.is_file():
        raise ValueError("Expected local private key file")
    key=private.read_bytes()
    bearer=signed_bearer(key)
    del key
    anonymous,anon_data=call("status",{})
    if anonymous!=403 or anon_data.get("error")!="ACCESS_DENIED":
        raise RuntimeError("Unsigned request not rejected: "+str(anonymous))
    status,data=call("status",{},bearer)
    if status!=200 or data.get("tenant")!="dodo-operations" or data.get("scopes")!=["read"]:
        raise RuntimeError("Signed gateway identity not accepted: "+str(status))
    status,example=call("policy/example",{},bearer)
    if status!=200:raise RuntimeError("Policy fixture unavailable: "+str(status))
    request={name:example[name] for name in ("pack","documents","retrieved","as_of")}
    status,full=call("policy/test",request,bearer)
    if status!=200 or full.get("verdict")!="ADMIT":
        raise RuntimeError("Expected ADMIT on complete evidence, got "+str(full.get("verdict")))
    request["retrieved"]=["ops-7.3","incident-summary","runbook-restart","ops-mirror-7.3"]
    status,partial=call("policy/test",request,bearer)
    if status!=200 or partial.get("verdict")!="INCONCLUSIVE":
        raise RuntimeError("Expected INCONCLUSIVE on incomplete evidence, got "+str(partial.get("verdict")))
    print("QUALITYRAG_PRIVATE_SIGNED_SMOKE_PASSED")
    print("unsigned=403 signed=200 complete=ADMIT incomplete=INCONCLUSIVE")
    print("signed_token_not_printed=true private_key_not_uploaded=true")

if __name__=="__main__":
    main()
