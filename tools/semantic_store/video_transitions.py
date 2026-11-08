"""Candidate state-transition reasoning over visual witness pairs.

A transition candidate is a *hypothesis* from two frames, not proof of
an action or its causal history. It may be used as a Semantic Event proposal
but never changes PackSpec admission or FF-RCT verdicts.
"""
from __future__ import annotations
import base64
import hashlib
import json
from urllib.request import Request, urlopen

from video_evidence import VideoEvidenceError

_ALLOWED = {"CHANGED", "UNCHANGED", "UNKNOWN"}
_MAX_PAIRS = 100


def _frame_witness(w):
    if not isinstance(w, dict) or w.get("modality") != "video":
        raise VideoEvidenceError("Transition requires visual witnesses")
    interval = w.get("interval")
    if not isinstance(interval, dict) or type(interval.get("start_ms")) is not int:
        raise VideoEvidenceError("Invalid visual timestamp")
    if not isinstance(w.get("id"), str) or not w["id"]:
        raise VideoEvidenceError("Invalid visual witness ID")
    digest = w.get("frame_sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(x not in "0123456789abcdef" for x in digest)):
        raise VideoEvidenceError("Frame hash required for transition")
    return w


def validate_transition(raw, before, after):
    """Validate structured comparative output without treating it as truth."""
    _frame_witness(before)
    _frame_witness(after)
    if before["interval"]["start_ms"] >= after["interval"]["start_ms"]:
        raise VideoEvidenceError("Before/after timestamps must be increasing")
    if not isinstance(raw, dict):
        raise VideoEvidenceError("Transition output must be JSON object")
    if set(raw) != {"entity", "attribute", "before", "after", "status"}:
        raise VideoEvidenceError("Unexpected transition fields")
    for field in ("entity", "attribute", "before", "after"):
        value = raw[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 160:
            raise VideoEvidenceError("Invalid transition field: " + field)
    if raw["status"] not in _ALLOWED:
        raise VideoEvidenceError("Invalid transition status")
    return {
        "entity": raw["entity"], "attribute": raw["attribute"],
        "before": raw["before"], "after": raw["after"],
        "status": raw["status"],
        "before_witness": before["id"], "after_witness": after["id"],
        "interval": {
            "start_ms": before["interval"]["start_ms"],
            "end_ms": after["interval"]["end_ms"]
        },
        "evidence_status": "UNVERIFIED_CANDIDATE",
        "causal_attribution": "UNKNOWN",
        "physical_constraint_verdict": "UNKNOWN"
    }


def vision_transition_ollama(before_bytes, after_bytes, *, model_name,
                             endpoint="http://127.0.0.1:11434"):
    if endpoint.rstrip("/") not in ("http://127.0.0.1:11434", "http://localhost:11434"):
        raise VideoEvidenceError("Only loopback Ollama is allowed")
    if not isinstance(model_name, str) or not model_name.strip() or len(model_name) > 128:
        raise VideoEvidenceError("Invalid model name")
    if not all(isinstance(x, bytes) and 0 < len(x) <= 10_000_000 for x in (before_bytes, after_bytes)):
        raise VideoEvidenceError("Invalid visual frame data")
    prompt = (
        "Compare these two still images, FIRST=before and SECOND=after. "
        "Describe at most one visibly supportable object attribute comparison. "
        "Do not infer motion, causal actions, identities, intent, or compliance. "
        "If the object is occluded, ambiguous, or missing, set status UNKNOWN. "
        "Return ONLY JSON with exactly these string properties: "
        "entity, attribute, before, after, status. "
        "status must be CHANGED, UNCHANGED, or UNKNOWN. "
        "Use 'unknown' for unsupported before/after values."
    )
    payload = json.dumps({"model": model_name, "stream": False,
        "format": "json", "options": {"temperature": 0},
        "messages": [{"role": "user", "content": prompt,
            "images": [base64.b64encode(before_bytes).decode("ascii"),
                       base64.b64encode(after_bytes).decode("ascii")]}]}).encode()
    request = Request(endpoint.rstrip("/") + "/api/chat", data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=120) as response:
        raw = response.read(1000001)
    if len(raw) > 1000000:
        raise VideoEvidenceError("Transition model response too large")
    try:
        parsed = json.loads(json.loads(raw)["message"]["content"])
    except (ValueError, KeyError, TypeError) as exc:
        raise VideoEvidenceError("Malformed JSON comparison") from exc
    return parsed


def propose_visual_transitions(frame_pairs, *, compare, max_pairs=_MAX_PAIRS):
    """Compare pre-extracted (witness, bytes) pairs, with bounded invocation.

    Return only candidate records. Never substitute a comparison for a
    temporal action witness, because intermediate frames are not observed.
    """
    if not isinstance(frame_pairs, list) or len(frame_pairs) > max_pairs or max_pairs < 1:
        raise VideoEvidenceError("Transition pair budget exceeded")
    results = []
    for before, after in frame_pairs:
        if (not isinstance(before, tuple) or not isinstance(after, tuple)
                or len(before) != 2 or len(after) != 2):
            raise VideoEvidenceError("Expected (witness, frame) tuples")
        a, bytes_a = before
        b, bytes_b = after
        _frame_witness(a)
        _frame_witness(b)
        if a["interval"]["start_ms"] >= b["interval"]["start_ms"]:
            raise VideoEvidenceError("Unordered visual pair")
        if (hashlib.sha256(bytes_a).hexdigest() != a["frame_sha256"]
                or hashlib.sha256(bytes_b).hexdigest() != b["frame_sha256"]):
            raise VideoEvidenceError("Frame bytes do not match witness hashes")
        results.append(validate_transition(compare(bytes_a, bytes_b), a, b))
    return results
