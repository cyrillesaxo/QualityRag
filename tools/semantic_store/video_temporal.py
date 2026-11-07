"""Deterministic temporal co-observation groups for unverified video evidence.

Grouping is not causal reasoning or verification. In particular overlapping
speech and frames cannot prove that speech accurately describes the frames.
"""
from __future__ import annotations

from video_evidence import VideoEvidenceError


def group_observations(witnesses, duration_ms, *, window_ms=5000, max_events=1000):
    if (type(duration_ms) is not int or duration_ms <= 0
            or type(window_ms) is not int or window_ms < 1
            or type(max_events) is not int or max_events < 1):
        raise VideoEvidenceError("Invalid temporal grouping configuration")
    if not isinstance(witnesses, list):
        raise VideoEvidenceError("Invalid witness list")
    if (duration_ms + window_ms - 1) // window_ms > 100_000:
        raise VideoEvidenceError("Temporal scan budget exceeded")
    groups = []
    # Preserve every timestamped witness through at least one candidate event.
    # A long speech interval may be indexed into multiple windows.
    for start in range(0, duration_ms, window_ms):
        end = min(duration_ms, start + window_ms)
        overlapping = []
        for w in witnesses:
            if not isinstance(w, dict) or not isinstance(w.get("interval"), dict):
                raise VideoEvidenceError("Invalid witness interval")
            span = w["interval"]
            a, b = span.get("start_ms"), span.get("end_ms")
            if type(a) is not int or type(b) is not int or not 0 <= a < b <= duration_ms:
                raise VideoEvidenceError("Invalid witness interval")
            if a < end and b > start:
                overlapping.append(w)
        if not overlapping:
            continue
        if len(groups) >= max_events:
            raise VideoEvidenceError("Temporal event budget exceeded")
        ids = [w["id"] for w in overlapping]
        if len(ids) != len(set(ids)):
            raise VideoEvidenceError("Duplicate witness id")
        modalities = sorted({w["modality"] for w in overlapping})
        groups.append({
            "id": f"co-observation-{start}",
            "label": "candidate co-observation: " + ", ".join(modalities),
            "interval": {"start_ms": start, "end_ms": end},
            "witnesses": ids,
            "entities": [], "attributes": [], "relations": [], "changes": [],
            "constraints": []
        })
    return groups
