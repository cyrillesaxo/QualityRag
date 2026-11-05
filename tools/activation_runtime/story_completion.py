"""Reviewer tooling for signed story-completion receipts.

audit.py accepts a story as DONE only with a completion envelope signed by a
trusted independent reviewer and bound to the story's exact criteria, module
hashes, implementation commit, merge commit and passing CI. Nothing in the
repository could produce such an envelope; this module does, but only with a
private key the reviewer supplies. It never generates or stores reviewer keys
and never signs on anyone's behalf.

    python -m tools.activation_runtime.story_completion pubkey  --key reviewer.pem --key-id alice-2026
    python -m tools.activation_runtime.story_completion draft   --story US-034 --implementation-commit SHA \\
        --merge-commit SHA --ci-url https://github.com/... --ci-receipt-sha256 HEX [--attest-all-criteria-met] > receipt.json
    python -m tools.activation_runtime.story_completion sign    --receipt receipt.json --key reviewer.pem \\
        --key-id alice-2026 --issued-at 2026-11-05T12:00:00Z --expires-at 2026-12-05T12:00:00Z > envelope.json
    python -m tools.activation_runtime.story_completion verify  --story US-034 --implementation-commit SHA \\
        --envelope envelope.json [--trust tools/activation_runtime/reviewer-trust.json] [--as-of ...]

``verify`` checks an envelope exactly as audit.py would, without editing
capabilities.json. Attaching a verified envelope and marking the story DONE is
a separate, reviewed change (see docs/STORY-CLOSURE-PACKETS.md).
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key

from .authority import ATTEST_SCHEMA, sign
from .common import HEX, fingerprint

ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES = ROOT / "tools/activation_runtime/capabilities.json"
TRUST = ROOT / "tools/activation_runtime/reviewer-trust.json"
TRUST_SCHEMA = "qualityrag.reviewer-trust/v1"
RECEIPT_SCHEMA = "qualityrag.story-completion/v1"
_COMMIT = re.compile("[0-9a-f]{40}")
_KEY_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


def _story(story_id: str, capabilities: Path = CAPABILITIES) -> dict:
    inventory = json.loads(Path(capabilities).read_text())
    for item in inventory["stories"]:
        if item["story_id"] == story_id:
            return item
    raise ValueError("Unknown story " + story_id)


def draft(story_id: str, *, implementation_commit: str, merge_commit: str, ci_url: str,
          ci_receipt_sha256: str, attest_all_criteria_met: bool = False,
          capabilities: Path = CAPABILITIES) -> dict:
    """Build the exact receipt audit.py expects. The reviewer must read it before signing."""
    item = _story(story_id, capabilities)
    if item["status"] == "DONE":
        raise ValueError(story_id + " is already DONE")
    for name, value in (("implementation commit", implementation_commit), ("merge commit", merge_commit)):
        if not isinstance(value, str) or not _COMMIT.fullmatch(value):
            raise ValueError("Full 40-character " + name + " required")
    if not isinstance(ci_url, str) or not ci_url.startswith("https://github.com/"):
        raise ValueError("CI URL must be a https://github.com/ link")
    if not isinstance(ci_receipt_sha256, str) or not HEX.fullmatch(ci_receipt_sha256):
        raise ValueError("CI receipt SHA-256 required")
    return {
        "schema": RECEIPT_SCHEMA,
        "story_id": story_id,
        "implementation_commit": implementation_commit,
        "module_inventory_sha256": fingerprint(item["modules"]),
        "acceptance_sha256": item["acceptance_sha256"],
        "merge_commit": merge_commit,
        "ci": {"status": "PASSED", "commit": implementation_commit, "url": ci_url,
               "receipt_sha256": ci_receipt_sha256},
        # Only an explicit reviewer flag sets MET; anything else is refused at signing time.
        "all_acceptance_criteria": "MET" if attest_all_criteria_met else "NOT_ATTESTED",
        "criteria": [c["text"] for c in item["criteria"]],
        "remaining_at_draft": item["remaining"],
    }


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    key = load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 private key required")
    return key


def public_key_entry(key: Ed25519PrivateKey, key_id: str, subject: str | None = None) -> dict:
    if not _KEY_ID.fullmatch(key_id):
        raise ValueError("Invalid key ID")
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    entry = {"key_id": key_id, "public_key": base64.b64encode(raw).decode()}
    if subject:
        entry["subject"] = subject
    return entry


def sign_receipt(receipt: dict, key: Ed25519PrivateKey, *, key_id: str, issued_at: str, expires_at: str,
                 capabilities: Path = CAPABILITIES) -> dict:
    """Sign a drafted receipt after re-checking it against the current inventory."""
    if receipt.get("all_acceptance_criteria") != "MET":
        raise ValueError("Receipt does not attest that all acceptance criteria are met; refusing to sign")
    fresh = draft(receipt["story_id"], implementation_commit=receipt["implementation_commit"],
                  merge_commit=receipt["merge_commit"], ci_url=receipt["ci"]["url"],
                  ci_receipt_sha256=receipt["ci"]["receipt_sha256"], attest_all_criteria_met=True,
                  capabilities=capabilities)
    if fresh != receipt:
        raise ValueError("Receipt no longer matches the story's current criteria or modules; redraft it")
    body = {"completion": receipt, "issued_at": issued_at, "expires_at": expires_at}
    return sign(body, key, key_id=key_id, schema=ATTEST_SCHEMA)


def load_trust(path: Path = TRUST) -> dict[str, Ed25519PublicKey]:
    data = json.loads(Path(path).read_text())
    if data.get("schema") != TRUST_SCHEMA or not isinstance(data.get("reviewers"), list):
        raise ValueError("Invalid reviewer trust store")
    keys = {}
    for entry in data["reviewers"]:
        kid = entry.get("key_id")
        if not isinstance(kid, str) or not _KEY_ID.fullmatch(kid) or kid in keys:
            raise ValueError("Invalid or duplicate reviewer key ID")
        keys[kid] = Ed25519PublicKey.from_public_bytes(base64.b64decode(entry["public_key"], validate=True))
    return keys


def verify(story_id: str, envelope: dict, *, implementation_commit: str, trusted_keys: dict,
           as_of: str | None = None, capabilities: Path = CAPABILITIES) -> dict:
    """Run audit.py's own completion check on a copy of the story; never edits the inventory."""
    from .audit import _completion

    item = copy.deepcopy(_story(story_id, capabilities))
    item["implementation_commit"] = implementation_commit
    item["completion_envelope"] = envelope
    as_of = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _completion(item, trusted_keys, as_of)
    return {"story_id": story_id, "envelope": "VALID_FOR_AUDIT", "as_of": as_of,
            "key_id": envelope["key_id"], "note": "Attach and mark DONE in a separate reviewed change."}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Signed story-completion receipts (reviewer-held keys only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pubkey"); p.add_argument("--key", required=True); p.add_argument("--key-id", required=True)
    p.add_argument("--subject")
    p = sub.add_parser("draft")
    for flag in ("--story", "--implementation-commit", "--merge-commit", "--ci-url", "--ci-receipt-sha256"):
        p.add_argument(flag, required=True)
    p.add_argument("--attest-all-criteria-met", action="store_true",
                   help="reviewer's explicit statement that every acceptance criterion is met")
    p = sub.add_parser("sign")
    for flag in ("--receipt", "--key", "--key-id", "--issued-at", "--expires-at"):
        p.add_argument(flag, required=True)
    p = sub.add_parser("verify")
    for flag in ("--story", "--implementation-commit", "--envelope"):
        p.add_argument(flag, required=True)
    p.add_argument("--trust", default=str(TRUST)); p.add_argument("--as-of")
    args = ap.parse_args(argv)
    if args.cmd == "pubkey":
        out = public_key_entry(_load_private_key(args.key), args.key_id, args.subject)
    elif args.cmd == "draft":
        out = draft(args.story, implementation_commit=args.implementation_commit, merge_commit=args.merge_commit,
                    ci_url=args.ci_url, ci_receipt_sha256=args.ci_receipt_sha256,
                    attest_all_criteria_met=args.attest_all_criteria_met)
    elif args.cmd == "sign":
        out = sign_receipt(json.loads(Path(args.receipt).read_text()), _load_private_key(args.key),
                           key_id=args.key_id, issued_at=args.issued_at, expires_at=args.expires_at)
    else:
        out = verify(args.story, json.loads(Path(args.envelope).read_text()),
                     implementation_commit=args.implementation_commit, trusted_keys=load_trust(Path(args.trust)),
                     as_of=args.as_of)
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
