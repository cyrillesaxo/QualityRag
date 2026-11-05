"""Local research-only bootstrap. Never creates independent review or deployment approval."""
import base64
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
from .authority import issue_access


def initialize(root):
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=False)
    issuer=Ed25519PrivateKey.generate();release=Ed25519PrivateKey.generate()
    for name,key in (("local-issuer",issuer),("local-release",release)):
        path=root/(name+".key")
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as f:f.write(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
    encode=lambda key:base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
    config={"access":{"local-issuer":encode(issuer)},"release":{"local-release":encode(release)},"minimum_sequence":1,"proposal_principals":[{"subject":"local-gardener","tenant":"local","scopes":["read"]}],"proposal_interval_seconds":60}
    (root/"public-keys.json").write_text(json.dumps(config,indent=2))
    now=datetime.now(timezone.utc)
    token=issue_access(subject="local-researcher",tenant="local",scopes=["read","write","review"],
        key=issuer,key_id="local-issuer",issued_at=now.isoformat(),expires_at=(now+timedelta(hours=24)).isoformat())
    fd=os.open(root/"access-token.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w") as f:json.dump(token,f)
    fd=os.open(root/"browser-token.txt",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w") as f:f.write(base64.urlsafe_b64encode(json.dumps(token,separators=(",",":")).encode()).decode().rstrip("="))
    return {"root":str(root),"keys":str(root/"public-keys.json"),"token_file":str(root/"access-token.json"),
            "browser_token_file":str(root/"browser-token.txt"),"mode":"LOCAL_RESEARCH_ONLY",
            "independent_review":"NOT_CREATED"}


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--root",required=True)
    args=parser.parse_args();print(json.dumps(initialize(args.root)))
