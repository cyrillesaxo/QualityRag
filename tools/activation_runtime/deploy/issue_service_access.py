"""Issue short-lived read-only signed *service* access for the Netlify gateway.

This is an offline operator action. The private key must remain off the
public backend and Netlify; tokens are written only to a fresh private file.
No stdout token output. Token rotation/revocation is an operator obligation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.authority import issue_access
from tools.activation_runtime.common import identity


def issue(*, private_key: str, key_id: str, subject: str, tenant: str,
          destination: str, minutes: int = 30, now: datetime | None = None):
    if type(minutes) is not int or not 5 <= minutes <= 60:
        raise ValueError("Service token validity must be 5-60 minutes")
    identity(key_id)
    identity(subject)
    identity(tenant)
    key_path = Path(private_key)
    key_stat = key_path.lstat()
    if not stat.S_ISREG(key_stat.st_mode) or (stat.S_IMODE(key_stat.st_mode) & 0o077):
        raise PermissionError("Signer private key must be a regular 0600 file")
    fd = os.open(str(key_path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        secret = handle.read(33)
    if len(secret) != 32:
        raise ValueError("Expected 32 raw Ed25519 private key bytes")
    signing_key = Ed25519PrivateKey.from_private_bytes(secret)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware issuance time required")
    stamp = lambda value: value.isoformat().replace("+00:00", "Z")
    envelope = issue_access(
        subject=subject, tenant=tenant, scopes=["read"],
        key=signing_key, key_id=key_id,
        issued_at=stamp(now), expires_at=stamp(now + timedelta(minutes=minutes)))
    # Protected output is never overwritten. Operator must transport it to
    # Netlify's restricted secret store through approved secret handling.
    output = Path(destination)
    fd = os.open(str(output), os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {"token_file": str(output), "scope": "read", "valid_minutes": minutes,
            "token_value_emitted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()
    result = issue(private_key=args.private_key,key_id=args.key_id,
                   subject=args.subject,tenant=args.tenant,
                   destination=args.output,minutes=args.minutes)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
