"""Fail-closed, geometric association of caller-supplied object detections.

This is NOT object detection, biometric identity, action recognition, or proof
of persistence through occlusion. Matching uses time, category and bounding-box
overlap only. Every resulting track is an UNVERIFIED hypothesis.
"""
from __future__ import annotations

import math
from video_evidence import VideoEvidenceError


def _label(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise VideoEvidenceError("Invalid " + name)
    return value


def _box(value):
    if (not isinstance(value, list) or len(value) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or not 0 <= v <= 1 for v in value)
            or value[0] >= value[2] or value[1] >= value[3]):
        raise VideoEvidenceError("Invalid normalized detection box")
    return list(value)


def intersection_over_union(left, right):
    a, b = _box(left), _box(right)
    width = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    overlap = width * height
    area_a = (a[2]-a[0]) * (a[3]-a[1])
    area_b = (b[2]-b[0]) * (b[3]-b[1])
    return overlap / (area_a + area_b - overlap)


def associate_detections(detections, witnesses, *, min_iou=0.5,
                         ambiguity_margin=0.1, max_gap_ms=6000,
                         max_detections=3000):
    """Return candidate tracks; never attach trust, physical action or identity.

    detections: [{witness_id, category, bbox, attributes:{str:str}}]
    Each witness must point to an actual, hashed video frame. Ambiguous matches
    start separate tracks rather than forcing same-entity continuity.
    """
    if (not isinstance(detections, list) or len(detections) > max_detections
            or not isinstance(witnesses, list)
            or type(max_detections) is not int or max_detections < 1
            or type(max_gap_ms) is not int or max_gap_ms < 1
            or type(min_iou) not in (int, float) or not 0 < min_iou <= 1
            or type(ambiguity_margin) not in (int, float)
            or not 0 <= ambiguity_margin <= 1):
        raise VideoEvidenceError("Invalid tracking configuration")
    indexed = {}
    for w in witnesses:
        if not isinstance(w, dict) or not isinstance(w.get("id"), str) or w["id"] in indexed:
            raise VideoEvidenceError("Invalid or duplicated witness ID")
        indexed[w["id"]] = w
    normalized = []
    seen = set()
    for i, raw in enumerate(detections):
        if not isinstance(raw, dict) or set(raw) != {"witness_id", "category", "bbox", "attributes"}:
            raise VideoEvidenceError("Invalid detection schema")
        wid = _label(raw["witness_id"], "witness_id")
        w = indexed.get(wid)
        if (not w or w.get("modality") != "video"
                or not isinstance(w.get("frame_sha256"), str)
                or len(w["frame_sha256"]) != 64):
            raise VideoEvidenceError("Detection requires a hashed visual witness")
        span = w.get("interval")
        if (not isinstance(span, dict) or type(span.get("start_ms")) is not int
                or type(span.get("end_ms")) is not int
                or not 0 <= span["start_ms"] < span["end_ms"]):
            raise VideoEvidenceError("Invalid witness interval")
        attrs = raw["attributes"]
        if not isinstance(attrs, dict) or len(attrs) > 30:
            raise VideoEvidenceError("Invalid attributes")
        for k, v in attrs.items():
            _label(k, "attribute name")
            _label(v, "attribute value")
        category = _label(raw["category"], "category")
        bbox = _box(raw["bbox"])
        key = (wid, category, tuple(bbox))
        if key in seen:
            raise VideoEvidenceError("Duplicate detection")
        seen.add(key)
        normalized.append({
            "input_index": i, "witness_id": wid, "category": category,
            "bbox": bbox, "attributes": dict(attrs),
            "start_ms": span["start_ms"], "end_ms": span["end_ms"]})
    # Processing is deterministic regardless of input order.
    normalized.sort(key=lambda d: (d["start_ms"], d["witness_id"],
                                   d["category"], d["bbox"], d["input_index"]))
    tracks = []
    by_time = {}
    for d in normalized:
        by_time.setdefault(d["start_ms"], []).append(d)

    for timestamp, batch in sorted(by_time.items()):
        candidates = []
        for di, det in enumerate(batch):
            for ti, track in enumerate(tracks):
                last = track["observations"][-1]
                gap = timestamp - last["start_ms"]
                if (gap <= 0 or gap > max_gap_ms
                        or det["category"] != track["category"]):
                    continue
                score = intersection_over_union(det["bbox"], last["bbox"])
                if score >= min_iou:
                    candidates.append((score, di, ti))
        # Reject conflicts on either endpoint, including near-ties.
        accepted = []
        for score, di, ti in candidates:
            alternatives_d = [s for s, d, t in candidates if d == di and t != ti]
            alternatives_t = [s for s, d, t in candidates if t == ti and d != di]
            if (any(s >= score - ambiguity_margin for s in alternatives_d)
                    or any(s >= score - ambiguity_margin for s in alternatives_t)):
                continue
            accepted.append((di, ti))
        claimed = set()
        for di, ti in accepted:
            tracks[ti]["observations"].append(batch[di])
            claimed.add(di)
        for di, det in enumerate(batch):
            if di not in claimed:
                tracks.append({"id": f"candidate-track-{len(tracks)}",
                               "category": det["category"], "observations": [det]})

    results = []
    for track in tracks:
        observations = [{k: v for k, v in d.items() if k != "input_index"}
                        for d in track["observations"]]
        changes = []
        for before, after in zip(observations, observations[1:]):
            for attr in sorted(set(before["attributes"]) | set(after["attributes"])):
                old, new = before["attributes"].get(attr), after["attributes"].get(attr)
                changes.append({
                    "attribute": attr,
                    "before": old if old is not None else "UNKNOWN",
                    "after": new if new is not None else "UNKNOWN",
                    "status": "UNKNOWN" if old is None or new is None else (
                        "CHANGED" if old != new else "UNCHANGED"),
                    "before_witness": before["witness_id"],
                    "after_witness": after["witness_id"],
                    "verification": "UNVERIFIED_CANDIDATE"})
        results.append({"id": track["id"], "category": track["category"],
                        "observations": observations, "changes": changes,
                        "association": "GEOMETRIC_HYPOTHESIS",
                        "identity_verified": False, "admission": "INCONCLUSIVE"})
    return results


def track_events(tracks):
    """Map multi-observation hypotheses to the existing video event contract."""
    if not isinstance(tracks, list):
        raise VideoEvidenceError("Invalid tracks")
    events = []
    for track in tracks:
        observations = track["observations"]
        if len(observations) < 2:
            continue
        ids = [o["witness_id"] for o in observations]
        if len(ids) != len(set(ids)):
            raise VideoEvidenceError("Track contains repeated frame witness")
        events.append({
            "id": "track-" + track["id"],
            "label": "candidate multi-frame track: " + track["category"],
            "interval": {"start_ms": observations[0]["start_ms"],
                         "end_ms": observations[-1]["end_ms"]},
            "witnesses": ids,
            "entities": [{"category": track["category"], "track_id": track["id"],
                          "identity_verified": False}],
            "changes": track["changes"],
            "constraints": [{"name": "object_continuity_verified",
                             "state": "UNKNOWN", "witnesses": ids}],
        })
    return events
