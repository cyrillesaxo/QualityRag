"""Offline policy signer. Run in governance-controlled environment, never Studio."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_policy


def sign_from_file(*, ir_file: str, private_key_pem: str, output_file: str,
                   key_id: str, service: str, environment: str, sequence: int,
                   issued_at: str, expires_at: str) -> dict:
    private_path = Path(private_key_pem)
    if private_path.is_symlink():
        raise ValueError("Refuse symlinked private key")
    if os.name == "posix" and (stat.S_IMODE(private_path.stat().st_mode) & 0o077):
        raise ValueError("Private key file must not be readable by group or others")
    key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Expected an Ed25519 private key")
    ir = json.loads(Path(ir_file).read_text(encoding="utf-8"))
    bundle = sign_policy(ir, key, key_id=key_id, service=service,
                         environment=environment, sequence=sequence,
                         issued_at=issued_at, expires_at=expires_at)
    data = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"
    # Refuse accidental overwrites. Signed bundle is public, private PEM isn't.
    descriptor = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(data)
    except BaseException:
        Path(output_file).unlink(missing_ok=True)
        raise
    return bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sign a reviewed typed IR for Studio promotion")
    for flag in ("ir-file", "private-key-pem", "output-file", "key-id",
                 "service", "environment", "issued-at", "expires-at"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--sequence", type=int, required=True)
    args = vars(parser.parse_args(argv))
    sign_from_file(**{k.replace("-", "_"): v for k, v in args.items()})
    print("Signed policy bundle written (private key was not copied).")


if __name__ == "__main__":
    main()
