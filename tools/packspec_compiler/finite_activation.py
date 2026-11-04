"""Exact finite JSON field transition; research execution, never domain admission.

Only flat scalar JSON objects are supported. Original bytes remain in host custody.
No arbitrary operators, plugins, model loading or attestation callbacks execute.
"""
from __future__ import annotations

import hashlib
import json
import math

from unified_gate import evaluate_unified

SCHEMA = "qualityrag.finite-activation/v0.1"
MAX_BYTES = 65536
MAX_FIELDS = 128


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate source key")
        result[key] = value
    return result


def parse_source(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("Bounded original bytes required")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    if not isinstance(value, dict) or not 1 <= len(value) <= MAX_FIELDS:
        raise ValueError("Bounded flat source object required")
    for key, item in value.items():
        if not key or len(key) > 512:
            raise ValueError("Bounded field name required")
        if type(item) not in (str, int, float, bool, type(None)):
            raise ValueError("Only scalar source fields supported")
        if type(item) is float and not math.isfinite(item):
            raise ValueError("Nonfinite source value")
    return value


def encode(raw, mapping):
    """Bijective rename of every field; no omission or normalization of values."""
    source = parse_source(raw)
    if (not isinstance(mapping, dict) or set(mapping) != set(source)
            or any(not isinstance(v, str) or not v or len(v) > 512 for v in mapping.values())
            or len(set(mapping.values())) != len(mapping)):
        raise ValueError("Total bijective field mapping required")
    return {
        "schema": SCHEMA, "runtime": "flat-json-rename/v1",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "mapping": dict(mapping),
        "payload": {mapping[k]: v for k, v in source.items()},
    }


def execute(raw, artifact, *, expected_artifact_sha256, ir, witnesses, as_of):
    """Check pinned compatibility, decode, compare every field, then use real gate.

    Caller must obtain expected_artifact_sha256 from trusted custody; a digest
    does not authenticate a publisher. This prototype never grants admission.
    Fallback exposes only a source reference, and never releases unverified output.
    """
    source = parse_source(raw)
    source_hash = hashlib.sha256(raw).hexdigest()
    trace = []
    reason = None
    reconstructed = None
    if not isinstance(artifact, dict) or digest(artifact) != expected_artifact_sha256:
        reason = "ARTIFACT_INTEGRITY_MISMATCH"
    elif artifact.get("schema") != SCHEMA or artifact.get("runtime") != "flat-json-rename/v1":
        reason = "INCOMPATIBLE_RUNTIME"
    elif artifact.get("source_sha256") != source_hash:
        reason = "SOURCE_MISMATCH"
    else:
        expected = encode(raw, artifact.get("mapping"))
        trace.append("COMPATIBILITY_CHECKED")
        # Canonical comparison distinguishes false from 0 and 1.0 from 1.
        if digest(expected) != digest(artifact):
            reason = "RECONSTRUCTION_MISMATCH"
        else:
            mapping = artifact["mapping"]
            reconstructed = {k: artifact["payload"][v] for k, v in mapping.items()}
            trace.extend(["TRANSITION_EXECUTED", "ALL_SOURCE_FIELDS_VERIFIED"])
    # Source hash above refers to data; the gate IR hash refers to policy bytes.
    # They intentionally remain separate identities.
    gate = evaluate_unified(ir, witnesses, {}, as_of)
    if reason or gate["verdict"] == "REFUSE":
        action = "REFUSE"
        trace.append("FALLBACK_REFERENCE_ONLY")
    else:
        action = "REQUIRES_REVIEW"
    return {
        "schema": "qualityrag.finite-activation-receipt/v0.1",
        "source_sha256": source_hash, "artifact_sha256": expected_artifact_sha256,
        "policy_ir_sha256": ir["ir_sha256"],
        "finite_constraint_result": "UNSAT" if reason else "SAT",
        "qualityrag_admission": "REFUSE" if action == "REFUSE" else "INCONCLUSIVE",
        "can_generate": False, "action": action, "reason": reason,
        "research_output": reconstructed if action != "REFUSE" else None,
        "fallback": {"source_sha256": source_hash, "released": False},
        "gate": gate, "trace": trace,
        "limitations": "Finite exact field equivalence only; no signed compatibility, semantic admission or video decoding.",
    }
