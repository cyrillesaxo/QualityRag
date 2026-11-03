"""Trusted-host bridge executing the original APX comparator in a bounded Node process.

This module never substitutes a Python semantic parser. An unavailable native
engine raises an error. It binds the returned redacted diagnostic to the exact
host-supplied source and candidate bytes; it cannot authenticate whether the
APX binary truly came from the canonical repository.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
from hashlib import sha256

RUNNER = Path(__file__).with_name("rct_native_semantic_runner.mjs")
SCHEMA = "qualityrag.native-semantic-transition/v1"
ALLOWED_KINDS = frozenset({
    "NUMBER", "DATE", "NEGATION", "MODALITY", "QUANTIFIER", "ACTOR",
    "RECIPIENT", "SCOPE", "AUTHORITY", "OBLIGATION", "LEGAL_EFFECT", "TERM",
})
ALLOWED_STATUSES = frozenset({"MISSING", "ADDED", "CHANGED"})
MAX_OUTPUT_BYTES = 30_000
MAX_TEXT_BYTES = 8192


class NativeSemanticUnavailable(RuntimeError):
    pass


def inspect_native_semantics(before: str, after: str, *,
                             apx_packages_root: str, timeout_seconds: int = 8) -> dict:
    """Run original APX source compiler, return version-bound redacted result.

    The host supplies the approved absolute APX package root; do NOT derive it
    from untrusted user input. The per-invocation HMAC key is ephemeral.
    """
    if (not isinstance(before, str) or not isinstance(after, str)
            or not before or not after
            or len(before.encode("utf-8")) > MAX_TEXT_BYTES
            or len(after.encode("utf-8")) > MAX_TEXT_BYTES):
        raise ValueError("Bounded nonempty UTF-8 texts required")
    if (not isinstance(apx_packages_root, str)
            or not Path(apx_packages_root).is_absolute()
            or not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or not 1 <= timeout_seconds <= 30):
        raise ValueError("Absolute trusted APX path and bounded timeout required")
    if not RUNNER.is_file():
        raise NativeSemanticUnavailable("Native semantic execution is not installed")
    # Do not forward deployment secrets, cloud tokens, or GitHub credentials
    # inherited from the Python host to a separate Node executable.
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "APX_PACKAGES_ROOT": apx_packages_root,
        "RCT_APX_HMAC_KEY_B64": base64.b64encode(
            secrets.token_bytes(32)).decode("ascii"),
    }
    payload = json.dumps({"beforeText": before, "afterText": after},
                         ensure_ascii=False, separators=(",", ":"))
    try:
        completed = subprocess.run(
            ["node", str(RUNNER)],
            input=payload, text=True,
            capture_output=True, env=env,
            timeout=timeout_seconds,
            check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise NativeSemanticUnavailable(
            "Canonical APX execution unavailable or exceeded time limit") from exc
    finally:
        env.pop("RCT_APX_HMAC_KEY_B64", None)
    if completed.returncode != 0 or len(completed.stdout.encode()) > MAX_OUTPUT_BYTES:
        raise NativeSemanticUnavailable("Canonical APX execution unavailable or invalid")
    try:
        native = json.loads(completed.stdout)
    except (ValueError, TypeError) as exc:
        raise NativeSemanticUnavailable("Invalid native comparator output") from exc
    expected_keys = {
        "schema", "original_engine_schema", "source_sha256",
        "candidate_sha256", "verdict", "observed_changes",
        "source_authority", "source_coverage", "semantic_completeness",
        "qualityrag_admission", "can_generate",
    }
    if (not isinstance(native, dict)
            or set(native) != expected_keys
            or native["schema"] != SCHEMA
            or native["original_engine_schema"] != "apx.semantic-text-transition/v0.1"
            or native["source_sha256"] != sha256(before.encode()).hexdigest()
            or native["candidate_sha256"] != sha256(after.encode()).hexdigest()
            or native["verdict"] not in ("REFUSE", "INCONCLUSIVE")
            or native["source_authority"] != "UNVERIFIED_HEURISTIC"
            or native["source_coverage"] != "BOUNDED_ENGLISH_PATTERNS"
            or native["semantic_completeness"] != "UNKNOWN"
            or native["qualityrag_admission"] != "INCONCLUSIVE"
            or native["can_generate"] is not False
            or not isinstance(native["observed_changes"], list)
            or len(native["observed_changes"]) > 256
            or any(not isinstance(x, dict)
                   or set(x) != {"kind", "status"}
                   or x["kind"] not in ALLOWED_KINDS
                   or x["status"] not in ALLOWED_STATUSES
                   for x in native["observed_changes"])):
        raise NativeSemanticUnavailable("Native comparator output violates trust contract")
    return native


def execute_dual_semantic_check(
        joined: dict, *, source_text: str, candidate_text: str,
        apx_packages_root: str, ir: dict, signed_policy: dict,
        signed_review: dict, policy_keys: dict, reviewer_keys: dict,
        minimum_sequence: int, service: str, environment: str,
        as_of: str, nonce_accepted) -> dict:
    """Directly execute canonical APX and reverify signed PackSpec review.

    The native output must match the exact text pair whose digests are bound by
    the original signed source-span review; no fallback if APX is unavailable.
    """
    if not isinstance(joined, dict) or not isinstance(joined.get("source_span_audit"), dict):
        raise ValueError("Source-bound reviewed candidate required")
    audit = joined["source_span_audit"]
    if (sha256(source_text.encode()).hexdigest() != audit.get("source_sha256")
            or sha256(candidate_text.encode()).hexdigest() != audit.get("candidate_sha256")):
        raise ValueError("Submitted document version differs from reviewed source spans")
    from rct_dual_semantic import combine_semantic_diagnostics
    native = inspect_native_semantics(
        source_text, candidate_text, apx_packages_root=apx_packages_root)
    return combine_semantic_diagnostics(
        joined, native, ir=ir, signed_policy=signed_policy,
        signed_review=signed_review, policy_keys=policy_keys,
        reviewer_keys=reviewer_keys, minimum_sequence=minimum_sequence,
        service=service, environment=environment, as_of=as_of,
        nonce_accepted=nonce_accepted)
