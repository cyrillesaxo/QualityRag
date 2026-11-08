"""Fail-closed, provider-neutral video semantic evidence contract.

Accepts *supplied* ASR and visual observations; never claims to perform ASR,
OCR, action recognition, source authentication, or physical constraint checks.
A visual claim needs visual evidence; absence of a detection is UNKNOWN.
"""
from __future__ import annotations
import hashlib
import json
import math

SCHEMA = "qualityrag.video-evidence/v1"
_STATES = {"OBSERVED", "CONTRADICTED", "UNKNOWN"}
_MODALITIES = {"audio", "video", "ocr", "sensor"}
_MAX_EVENTS = 1000
_MAX_WITNESSES = 5000


class VideoEvidenceError(ValueError):
    pass


def _object(value, label):
    if not isinstance(value, dict):
        raise VideoEvidenceError(f"{label} must be an object")
    return value


def _string(value, label, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise VideoEvidenceError(f"Invalid {label}")
    return value


def _interval(value, duration_ms):
    if (not isinstance(value, dict) or type(value.get("start_ms")) is not int
            or type(value.get("end_ms")) is not int
            or not 0 <= value["start_ms"] < value["end_ms"] <= duration_ms):
        raise VideoEvidenceError("Invalid time interval")
    return {"start_ms": value["start_ms"], "end_ms": value["end_ms"]}


def _confidence(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise VideoEvidenceError("Confidence must be finite and between 0 and 1")
    return float(value)


def compile_video_evidence(*, source_id, revision, media_sha256, duration_ms,
                           witnesses, events, model_receipts=None):
    """Compile reviewed or machine-proposed observations without elevating truth.

    Input witnesses: id, modality, interval, text, provider, optional confidence,
    optional frame_sha256 and region [x1,y1,x2,y2] in normalized coordinates.
    Input events: id, label, interval, witnesses (ids), optional entities,
    attributes, relations, changes and constraints. Each constraint carries
    name, state and witness ids. UNKNOWN is the default and cannot be
    upgraded based on transcript speech alone.
    """
    _string(source_id, "source_id")
    _string(revision, "revision")
    if (not isinstance(media_sha256, str) or len(media_sha256) != 64
            or any(c not in "0123456789abcdef" for c in media_sha256)):
        raise VideoEvidenceError("media_sha256 must be lowercase SHA-256")
    if type(duration_ms) is not int or not 0 < duration_ms <= 7 * 24 * 3600 * 1000:
        raise VideoEvidenceError("Invalid duration_ms")
    if not isinstance(witnesses, list) or len(witnesses) > _MAX_WITNESSES:
        raise VideoEvidenceError("Invalid witness list")
    if not isinstance(events, list) or len(events) > _MAX_EVENTS:
        raise VideoEvidenceError("Invalid event list")
    indexed = {}
    out_witnesses = []
    for raw in witnesses:
        w = _object(raw, "witness")
        wid = _string(w.get("id"), "witness.id")
        if wid in indexed:
            raise VideoEvidenceError("Duplicate witness id")
        modality = w.get("modality")
        if modality not in _MODALITIES:
            raise VideoEvidenceError("Unsupported modality")
        span = _interval(w.get("interval"), duration_ms)
        text = _string(w.get("text"), "witness.text", 10000)
        provider = _string(w.get("provider"), "witness.provider")
        item = {"id": wid, "modality": modality, "interval": span,
                "text": text, "provider": provider, "confidence": _confidence(w.get("confidence")),
                "admission": "UNVERIFIED_OBSERVATION"}
        if "frame_sha256" in w:
            frame = w["frame_sha256"]
            if not isinstance(frame, str) or len(frame) != 64 or any(c not in "0123456789abcdef" for c in frame):
                raise VideoEvidenceError("Invalid frame SHA-256")
            if modality not in ("video", "ocr"):
                raise VideoEvidenceError("Frame witness must be visual")
            item["frame_sha256"] = frame
        if "region" in w:
            region = w["region"]
            if (modality not in ("video", "ocr") or not isinstance(region, list)
                    or len(region) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in region)
                    or region[0] >= region[2] or region[1] >= region[3]):
                raise VideoEvidenceError("Invalid normalized visual region")
            item["region"] = list(region)
        indexed[wid] = item
        out_witnesses.append(item)

    def refs(values, span):
        if not isinstance(values, list) or len(values) != len(set(map(str, values))):
            raise VideoEvidenceError("Invalid witness references")
        for ref in values:
            if not isinstance(ref, str) or ref not in indexed:
                raise VideoEvidenceError("Missing witness reference")
            wspan = indexed[ref]["interval"]
            if wspan["end_ms"] <= span["start_ms"] or wspan["start_ms"] >= span["end_ms"]:
                raise VideoEvidenceError("Witness outside event interval")
        return list(values)

    out_events = []
    ids = set()
    for raw in events:
        e = _object(raw, "event")
        eid = _string(e.get("id"), "event.id")
        if eid in ids:
            raise VideoEvidenceError("Duplicate event id")
        ids.add(eid)
        span = _interval(e.get("interval"), duration_ms)
        evidences = refs(e.get("witnesses", []), span)
        if not evidences:
            raise VideoEvidenceError("Events require evidence references")
        constraints = []
        for c in e.get("constraints", []):
            c = _object(c, "constraint")
            name = _string(c.get("name"), "constraint.name")
            state = c.get("state", "UNKNOWN")
            if state not in _STATES:
                raise VideoEvidenceError("Unsupported constraint state")
            c_refs = refs(c.get("witnesses", []), span)
            if state != "UNKNOWN" and not c_refs:
                raise VideoEvidenceError("Asserted constraint requires witnesses")
            if state == "OBSERVED" and not any(indexed[r]["modality"] in ("video", "ocr", "sensor") for r in c_refs):
                raise VideoEvidenceError("Speech alone cannot verify a physical constraint")
            constraints.append({"name": name, "state": state, "witnesses": c_refs})
        annotations = {}
        for field in ("entities", "attributes", "relations", "changes"):
            value = e.get(field, [])
            if not isinstance(value, list) or len(value) > 100:
                raise VideoEvidenceError(f"Invalid {field}")
            # Keep proposals as uninterpreted, JSON-safe data; no inference here.
            if any(not isinstance(v, (dict, str)) for v in value):
                raise VideoEvidenceError(f"Invalid {field} entry")
            annotations[field] = value
        out_events.append({"id": eid, "label": _string(e.get("label"), "event.label"),
                           "interval": span, "witnesses": evidences,
                           "constraints": constraints, **annotations,
                           "admission": "CANDIDATE_REQUIRES_REVIEW"})
    if model_receipts is None:
        model_receipts = []
    if not isinstance(model_receipts, list) or any(not isinstance(r, dict) for r in model_receipts):
        raise VideoEvidenceError("Invalid model receipts")
    result = {"schema": SCHEMA,
              "source": {"source_id": source_id, "revision": revision,
                         "media_sha256": media_sha256, "duration_ms": duration_ms},
              "witnesses": out_witnesses, "events": out_events,
              "model_receipts": model_receipts,
              "governance": {"packspec": "NOT_BOUND", "admission": "INCONCLUSIVE",
                             "semantic_interpretation": "UNVERIFIED",
                             "source_authenticity": "UNVERIFIED",
                             "source_media_embedded": False}}
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    result["fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


def inspect_constraints(artifact):
    """List inconclusive conditions without inferring an absence from missing frames."""
    _object(artifact, "artifact")
    fingerprint = artifact.get("fingerprint")
    body = dict(artifact)
    body.pop("fingerprint", None)
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if artifact.get("schema") != SCHEMA or hashlib.sha256(canonical.encode()).hexdigest() != fingerprint:
        raise VideoEvidenceError("Invalid or modified artifact")
    return [{"event_id": e["id"], "constraint": c["name"], "state": c["state"]}
            for e in artifact["events"] for c in e["constraints"] if c["state"] == "UNKNOWN"]
