"""Explicit PackSpec source resolution (v0.1).

No fallback between embedded/property/file/Studio modes. Studio is a local
development registry, not a production-grade identity or signature service.
"""
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from urllib.parse import urlparse
from typing import Callable

MAX_BYTES = 262_144
SEGMENT = re.compile(r"^[a-zA-Z0-9._-]+$")


def validate(pack):
    if not isinstance(pack, dict) or not isinstance(pack.get("id"), str) or not pack["id"].strip() or (
        not isinstance(pack.get("version"), str) or not pack["version"].strip()
    ) or not isinstance(pack.get("requirements"), list) or not pack["requirements"]:
        raise ValueError("Invalid PackSpec")
    ids = set()
    for req in pack["requirements"]:
        if not isinstance(req, dict) or not isinstance(req.get("id"), str) or not req["id"] or req["id"] in ids:
            raise ValueError("Invalid PackSpec requirement")
        ids.add(req["id"])
        for key, minimum in (("min_independent_sources", 1), ("max_age_seconds", 0)):
            if key in req and (type(req[key]) is not int or req[key] < minimum):
                raise ValueError("Invalid PackSpec threshold")
    return pack


def _parse(text):
    return validate(json.loads(text))


def internal(pack):
    """Snapshot application-owned policy at configuration time."""
    snapshot = json.dumps(validate(pack), separators=(",", ":"), ensure_ascii=False)
    return lambda: _parse(snapshot)


def property_source(text):
    """Load and validate an injected JSON property; snapshot on initialization."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("PackSpec property absent")
    return internal(_parse(text))


def file_source(path):
    """Read the selected JSON file each time, without implicit fallback."""
    path = Path(path)
    def load():
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("PackSpec file too large")
        return _parse(path.read_text(encoding="utf-8"))
    return load


def studio_source(base_url, token, service_id, environment):
    """Resolve an approved policy from the local QualityRag Studio registry."""
    url = urlparse(base_url)
    if not (url.scheme == "https" or
            (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1"))):
        raise ValueError("Studio requires HTTPS outside loopback")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("Studio URL must not contain userinfo, query or fragment")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Studio token required")
    if not (SEGMENT.fullmatch(service_id or "") and SEGMENT.fullmatch(environment or "")):
        raise ValueError("Invalid service/environment")
    endpoint = base_url.rstrip("/") + "/v1/resolve/" + service_id + "/" + environment

    def load():
        request = urllib.request.Request(endpoint, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError("Studio policy resolution failed")
            payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise RuntimeError("Studio response too large")
        envelope = json.loads(payload)
        if (envelope.get("status") != "APPROVED" or envelope.get("serviceId") != service_id or
                envelope.get("environment") != environment):
            raise RuntimeError("Unapproved or mismatched Studio policy")
        pack = validate(envelope.get("policy"))
        digest = envelope.get("sha256")
        # Match the current Node.js registry's JSON.stringify(policy) hashing convention.
        actual = hashlib.sha256(json.dumps(pack, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest) or digest != actual:
            raise RuntimeError("Studio policy integrity failure")
        return pack
    return load


def from_properties(props, internal_pack=None):
    """Choose exactly one explicit policy authority. No catch/fallback."""
    mode = props.get("qualityrag.packspec.source", "").strip().lower()
    if mode == "internal":
        return internal(internal_pack)
    if mode == "property":
        return property_source(props.get("qualityrag.packspec.json"))
    if mode == "file":
        path = props.get("qualityrag.packspec.path")
        if not path:
            raise ValueError("PackSpec path missing")
        return file_source(path)
    if mode == "studio":
        return studio_source(*(require(props, key) for key in (
            "qualityrag.registry.url", "qualityrag.registry.token",
            "qualityrag.service-id", "qualityrag.environment")))
    raise ValueError("Explicit PackSpec source required")


def require(props, key):
    value = props.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing " + key)
    return value
