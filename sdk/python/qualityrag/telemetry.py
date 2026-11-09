"""Opt-in, metadata-only QualityRAG registry emission.

No background telemetry or implicit network traffic. The caller must supply a
scoped ingestion credential and opaque source/origin tokens. The registry
resolves its own approved policy and recomputes the outcome; this helper does
not authorize an answer or prove a source.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class EvidenceTelemetryError(RuntimeError):
    """Registry telemetry failed; do not interpret absence as a passed check."""


_OPAQUE = re.compile(r"^(ev|org|src)_[0-9a-f]{24,64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def emit_evidence(
    base_url: str,
    bearer_token: str,
    *,
    service_id: str,
    environment: str,
    request_id: str,
    trace_id: str,
    evidence: list[dict[str, Any]],
    expected_verdict: str | None = None,
    timeout_seconds: float = 4.0,
) -> dict[str, Any]:
    """Send an explicit bounded evidence event and return the registry verdict.

    The approved service/environment PackSpec is resolved on the registry.
    Never put raw text, prompts, personal data or secrets into source IDs.
    The origin tokens must come from a governed ingestion process; this API
    does not authenticate their claims.
    """
    if not isinstance(base_url, str) or not isinstance(bearer_token, str) or not bearer_token:
        raise ValueError("registry URL and ingestion token required")
    url = urllib.parse.urlsplit(base_url)
    if url.username or url.password or url.query or url.fragment or not url.hostname:
        raise ValueError("invalid registry URL")
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
    ):
        raise ValueError("registry must use HTTPS or localhost HTTP")
    if url.path not in {"", "/"}:
        raise ValueError("base_url must not contain a path")
    if not all(isinstance(v, str) and _ID.fullmatch(v) for v in
               (service_id, environment, request_id, trace_id)):
        raise ValueError("invalid event identifiers")
    if expected_verdict is not None and expected_verdict not in {
        "ADMIT", "REFUSE", "INCONCLUSIVE"
    }:
        raise ValueError("invalid expected verdict")
    if not isinstance(timeout_seconds, (float, int)) or not (0 < timeout_seconds <= 30):
        raise ValueError("invalid timeout")
    if not isinstance(evidence, list) or len(evidence) > 100:
        raise ValueError("invalid evidence")
    required = {"id", "requirement_id", "origin", "source_ref", "status", "observed_at"}
    for row in evidence:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("only approved evidence metadata fields may be emitted")
        if not all(isinstance(row[k], str) for k in required):
            raise ValueError("metadata values must be strings")
        if not all(_OPAQUE.fullmatch(row[k]) for k in ("id", "origin", "source_ref")):
            raise ValueError("opaque evidence tokens are required")
        if row["status"] not in {"SUPPORTS", "CONTRADICTS", "UNKNOWN"}:
            raise ValueError("invalid evidence status")
    data = {
        "serviceId": service_id,
        "environment": environment,
        "requestId": request_id,
        "traceId": trace_id,
        "evidence": evidence,
    }
    body = json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if len(body) > 180_000:
        raise ValueError("evidence payload too large")
    endpoint = urllib.parse.urlunsplit(
        (url.scheme, url.netloc, "/v1/evidence/evaluations", "", "")
    )
    req = urllib.request.Request(
        endpoint, data=body,
        headers={
            "Authorization": "Bearer " + bearer_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_seconds)) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise EvidenceTelemetryError("telemetry HTTP " + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise EvidenceTelemetryError("telemetry collector unreachable or invalid response") from None
    if result.get("declaredOriginsOnly") is not True or result.get("verdict") not in {
        "ADMIT", "REFUSE", "INCONCLUSIVE"
    }:
        raise EvidenceTelemetryError("invalid telemetry result contract")
    if expected_verdict is not None and result["verdict"] != expected_verdict:
        raise EvidenceTelemetryError("local/registry verdict mismatch")
    return result
