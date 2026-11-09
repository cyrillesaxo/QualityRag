#!/usr/bin/env python3
"""Generate two separate raw Ed25519 signing keys OFFLINE on Windows.

Run on the operator workstation, NEVER on the governance server.
Requires: py -m pip install cryptography
Only authority.json (public verification keys) is uploaded to the server.
Private keys remain in a new ACL-restricted local folder.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption

IDS = {"access": "production-access-1", "release": "production-release-1"}

def restrict_windows_directory(path: Path) -> None:
    account = subprocess.run(["whoami"], capture_output=True, text=True, check=True).stdout.strip()
    if not account or "\n" in account:
        raise RuntimeError("Cannot determine Windows account for private-key ACL")
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", account + ":(OI)(CI)F"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Refusing to create keys: private directory ACL failed. " + result.stderr)

def generate(directory: Path) -> Path:
    if os.name != "nt":
        raise RuntimeError("Use only on the operator's Windows computer")
    if directory.exists():
        raise FileExistsError("Refusing to reuse or overwrite private-key directory: " + str(directory))
    directory.mkdir(mode=0o700, parents=False)
    restrict_windows_directory(directory)
    authority = {"access": {}, "release": {}, "minimum_sequence": 1, "proposal_principals": []}
    for purpose, kid in IDS.items():
        private = Ed25519PrivateKey.generate()
        raw_private = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        raw_public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        key_file = directory / (kid + ".key")
        with key_file.open("xb") as f:
            f.write(raw_private)
        authority[purpose][kid] = base64.b64encode(raw_public).decode("ascii")
    public_dir = directory / "UPLOAD_PUBLIC_ONLY"
    public_dir.mkdir(exist_ok=False)
    authority_file = public_dir / "authority.json"
    with authority_file.open("x", encoding="utf-8") as f:
        json.dump(authority, f, sort_keys=True, indent=2)
        f.write("\n")
    print("PUBLIC_AUTHORITY_FILE=" + str(authority_file))
    print("PRIVATE_KEYS_REMAIN_IN=" + str(directory))
    print("UPLOAD ONLY UPLOAD_PUBLIC_ONLY/authority.json; NEVER upload *.key.")
    return authority_file

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: py offline_windows_keygen.py C:\\Users\\YOUR_USER\\QualityRAG-keys")
    generate(Path(sys.argv[1]).expanduser().resolve())
