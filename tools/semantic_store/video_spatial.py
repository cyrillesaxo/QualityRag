"""Optional local vision-model spatial proposals, never trusted detections.

The local VLM proposes bounding boxes for individual sampled frames. Boxes
are strictly validated but NOT spatially verified: VLM coordinates can be wrong.
Caller-supplied annotations and detector-model outputs have identical
unverified admission. No person re-identification or biometric claims.
"""
from __future__ import annotations
import base64
import json
import math
from urllib.request import Request, urlopen

from video_evidence import VideoEvidenceError

MAX_PER_FRAME = 20
PROMPT = (
    "Inspect this single image. Return ONLY JSON with a top-level 'objects' "
    "array (maximum 20). Each entry has exactly: category (brief generic "
    "object class), bbox ([left,top,right,bottom] normalized 0..1), "
    "attributes (object whose keys/values are short strings). "
    "Include only visually supported objects; no inferred action, movement, "
    "physical safety compliance, identity, demographic category or intent. "
    "If localization is uncertain omit that object. Do not identify people."
)


def validate_spatial_proposals(raw, *, max_objects=MAX_PER_FRAME):
    if type(max_objects) is not int or not 1 <= max_objects <= 50:
        raise VideoEvidenceError("Invalid object budget")
    if not isinstance(raw, dict) or set(raw) != {"objects"} or not isinstance(raw["objects"], list):
        raise VideoEvidenceError("Invalid spatial output envelope")
    if len(raw["objects"]) > max_objects:
        raise VideoEvidenceError("Too many spatial proposals")
    results = []
    used = set()
    for item in raw["objects"]:
        if not isinstance(item, dict) or set(item) != {"category", "bbox", "attributes"}:
            raise VideoEvidenceError("Unexpected spatial proposal fields")
        category, bbox, attributes = item["category"], item["bbox"], item["attributes"]
        if not isinstance(category, str) or not category.strip() or len(category) > 128:
            raise VideoEvidenceError("Invalid category")
        if (not isinstance(bbox, list) or len(bbox) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in bbox)
                or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]):
            raise VideoEvidenceError("Invalid normalized box")
        if not isinstance(attributes, dict) or len(attributes) > 30:
            raise VideoEvidenceError("Invalid attributes")
        for k, v in attributes.items():
            if not isinstance(k, str) or not k.strip() or len(k) > 128:
                raise VideoEvidenceError("Invalid attribute key")
            if not isinstance(v, str) or not v.strip() or len(v) > 128:
                raise VideoEvidenceError("Invalid attribute value")
        key = (category, tuple(bbox))
        if key in used:
            raise VideoEvidenceError("Repeated spatial proposal")
        used.add(key)
        results.append({"category": category, "bbox": list(bbox),
                        "attributes": dict(attributes)})
    return results


def detect_objects_ollama_local(frame_bytes, *, model_name,
                                endpoint="http://127.0.0.1:11434"):
    if endpoint.rstrip("/") not in ("http://127.0.0.1:11434", "http://localhost:11434"):
        raise VideoEvidenceError("Only loopback Ollama is supported")
    if not isinstance(model_name, str) or not model_name.strip() or len(model_name) > 128:
        raise VideoEvidenceError("Invalid vision model")
    if not isinstance(frame_bytes, bytes) or not 0 < len(frame_bytes) <= 10_000_000:
        raise VideoEvidenceError("Invalid frame")
    message = json.dumps({
        "model": model_name, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": PROMPT,
                      "images": [base64.b64encode(frame_bytes).decode("ascii")]}]
    }).encode()
    request = Request(endpoint.rstrip("/") + "/api/chat", data=message,
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=120) as response:
        payload = response.read(1_000_001)
    if len(payload) > 1_000_000:
        raise VideoEvidenceError("Spatial output too large")
    try:
        envelope = json.loads(payload)
        proposals = json.loads(envelope["message"]["content"])
    except (KeyError, ValueError, TypeError) as exc:
        raise VideoEvidenceError("Invalid local vision spatial response") from exc
    return validate_spatial_proposals(proposals)


def frame_detections(raw, witness_id):
    """Ground proposed boxes to an existing hashed sampled-frame witness ID."""
    if not isinstance(witness_id, str) or not witness_id:
        raise VideoEvidenceError("Invalid frame witness reference")
    return [{"witness_id": witness_id, **obj}
            for obj in validate_spatial_proposals({"objects": raw})]
