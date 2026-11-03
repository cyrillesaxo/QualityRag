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


def execute_relational_semantic_check(
        joined: dict, *, source_text: str, candidate_text: str,
        source_facts: list[dict], candidate_facts: list[dict],
        apx_packages_root: str, ir: dict, signed_policy: dict,
        signed_span_review: dict, signed_role_review: dict,
        policy_keys: dict, span_reviewer_keys: dict, role_reviewer_keys: dict,
        minimum_sequence: int, service: str, environment: str,
        as_of: str, nonce_accepted) -> dict:
    """Native lexical + signed span + signed typed role conservation.

    A lexical INCONCLUSIVE must not override a reviewed role violation.
    All three checks bind the identical document SHA-256 and governing IR.
    None establishes complete semantic extraction or truth of annotations.

    The signed span and role reviews use independent one-use nonces; validation
    is not an atomic transaction. The host must manage retry/re-sign on a
    partially spent nonce after a later failure.
    """
    from rct_signed_role_grammar import (
        proposed_role_review, verify_signed_role_review)
    from rct_signed_span_review import proposed_inventory_review
    from rct_dual_semantic import combine_semantic_diagnostics
    from store import digest
    if (not isinstance(joined, dict)
            or not isinstance(joined.get("source_span_audit"), dict)
            or sha256(source_text.encode()).hexdigest() !=
               joined["source_span_audit"].get("source_sha256")
            or sha256(candidate_text.encode()).hexdigest() !=
               joined["source_span_audit"].get("candidate_sha256")):
        raise ValueError("Source and candidate must match reviewed documents")
    if (not isinstance(signed_role_review,dict)
            or not isinstance(signed_span_review,dict)
            or not isinstance(signed_policy,dict)
            or len({
                signed_role_review.get("key_id"),
                signed_span_review.get("key_id"),
                signed_policy.get("key_id"),
            }) != 3):
        raise ValueError("Independent policy, span and role reviewer identities required")
    # Preflight the exact version and signed observation payloads so malformed
    # document/inventory differences fail BEFORE native execution and replay.
    role_draft=proposed_role_review(
        source=source_text,candidate=candidate_text,
        source_facts=source_facts,candidate_facts=candidate_facts,ir=ir)
    span_draft=proposed_inventory_review(joined,ir)
    from signed_bundles import ATTEST_SCHEMA, verify
    role_body=verify(signed_role_review,role_reviewer_keys,schema=ATTEST_SCHEMA)
    span_body=verify(signed_span_review,span_reviewer_keys,schema=ATTEST_SCHEMA)
    if (role_body.get("observations") != {
            "typed_role_graph_review":dict(
                role_draft,review_status="REVIEWED_FINITE_ROLE_BINDINGS")}
            or role_body.get("witnesses") != []
            or span_body.get("observations") != {
                "source_span_inventory_review":dict(
                    span_draft,review_status="REVIEWED_FINITE_SCOPE")}
            or span_body.get("witnesses") != []):
        raise ValueError("Signed role or source-span claims differ from source versions")
    native=inspect_native_semantics(
        source_text,candidate_text,apx_packages_root=apx_packages_root)
    # The role checker verifies its own signed policy, actual original bytes,
    # trusted reviewer key and nonce. The original native result is never a
    # substitute for the signed role semantics.
    relational=verify_signed_role_review(
        source=source_text,candidate=candidate_text,
        source_facts=source_facts,candidate_facts=candidate_facts,
        ir=ir,signed_policy=signed_policy,signed_review=signed_role_review,
        policy_keys=policy_keys,reviewer_keys=role_reviewer_keys,
        minimum_sequence=minimum_sequence,service=service,
        environment=environment,as_of=as_of,
        nonce_accepted=nonce_accepted)
    lexical_and_spans=combine_semantic_diagnostics(
        joined,native,ir=ir,signed_policy=signed_policy,
        signed_review=signed_span_review,policy_keys=policy_keys,
        reviewer_keys=span_reviewer_keys,
        minimum_sequence=minimum_sequence,service=service,
        environment=environment,as_of=as_of,
        nonce_accepted=nonce_accepted)
    if (relational["source_sha256"] != lexical_and_spans["source_text_sha256"]
            or relational["candidate_sha256"] != lexical_and_spans["candidate_text_sha256"]
            or relational["governing_ir_sha256"] != ir["ir_sha256"]):
        raise ValueError("Relational and native document/PackSpec versions differ")
    verdict=("REFUSE" if "REFUSE" in (
        relational["verdict"],lexical_and_spans["verdict"])
             else "INCONCLUSIVE")
    combined={
        "schema":"rct.native-relational-semantic-governance/v0.1",
        "source_sha256":relational["source_sha256"],
        "candidate_sha256":relational["candidate_sha256"],
        "governing_ir_sha256":ir["ir_sha256"],
        "native_span_receipt_sha256":lexical_and_spans["fingerprint"],
        "signed_role_receipt_sha256":relational["fingerprint"],
        "native_lexical_verdict":lexical_and_spans["native_verdict"],
        "signed_role_verdict":relational["verdict"],
        "signed_span_verdict":lexical_and_spans["reviewed_span_verdict"],
        "verdict":verdict,
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
        "semantic_completeness":"UNKNOWN",
        "publisher_authority":"NOT_ESTABLISHED",
        "role_extraction":"EXTERNAL_REVIEWED_ANNOTATIONS_NOT_AUTOMATED",
        "native_runtime_authority":"NOT_INDEPENDENTLY_ATTESTED",
    }
    combined["fingerprint"]=digest(combined)
    return combined
