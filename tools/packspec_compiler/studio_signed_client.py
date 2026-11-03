"""Resolve exact signed policies from Studio; never use the legacy unsigned endpoint."""
from __future__ import annotations

import json
import re
from urllib import request, error
from urllib.parse import urlsplit

from signed_gate import guarded_generate_signed
from signed_bundles import SignatureError, MAX_DOCUMENT_BYTES

_SEGMENT = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

class SignedStudioError(ValueError):
    pass


def fetch_signed_policy(base_url: str, token: str, service: str, environment: str,
                        *, timeout: float = 5) -> dict:
    """Get untrusted JSON for subsequent local verification with pinned public keys."""
    parts = urlsplit(base_url)
    if not ((parts.scheme == "https" and parts.hostname) or
            (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost"))):
        raise SignedStudioError("HTTPS required outside loopback")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise SignedStudioError("Invalid registry URL")
    if (not isinstance(token, str) or not token.strip() or not _SEGMENT.fullmatch(service) or
            not _SEGMENT.fullmatch(environment)):
        raise SignedStudioError("Invalid registry access configuration")
    url = base_url.rstrip("/") + "/v1/signed/resolve/" + service + "/" + environment
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    req = request.Request(url, headers=headers, method="GET")
    # Redirects may forward the bearer token; disallow all redirects.
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise SignedStudioError("Registry redirect refused")
    opener = request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as response:
            if response.status != 200:
                raise SignedStudioError("Unexpected signed registry status")
            body = response.read(MAX_DOCUMENT_BYTES + 1)
    except error.HTTPError as exc:
        raise SignedStudioError("Signed registry unavailable") from exc
    if len(body) > MAX_DOCUMENT_BYTES:
        raise SignedStudioError("Registry response too large")
    try:
        result = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SignedStudioError("Invalid signed registry response") from exc
    if not isinstance(result, dict) or result.get("status") != "PUBLISHED":
        raise SignedStudioError("Signed policy not published")
    if result.get("serviceId") != service or result.get("environment") != environment:
        raise SignedStudioError("Signed registry binding mismatch")
    bundle = result.get("signedPolicy")
    if not isinstance(bundle, dict):
        raise SignedStudioError("Missing signed policy")
    if result.get("sequence") != bundle.get("payload", {}).get("sequence"):
        raise SignedStudioError("Signed registry sequence mismatch")
    return bundle


def guarded_generate_from_studio(
    base_url: str, registry_token: str, *,
    policy_keys: dict, attestor_keys: dict, service: str, environment: str,
    minimum_sequence: int, nonce_accepted, signed_observations: dict,
    witnesses: list[dict], observations: dict, as_of: str, generator,
) -> dict:
    """Fail closed: retrieve signed policy, verify it, then use the signed unified gate."""
    bundle = fetch_signed_policy(base_url, registry_token, service, environment)
    return guarded_generate_signed(
        signed_policy=bundle, signed_observations=signed_observations,
        policy_keys=policy_keys, attestor_keys=attestor_keys, service=service,
        environment=environment, minimum_sequence=minimum_sequence,
        nonce_accepted=nonce_accepted, witnesses=witnesses,
        observations=observations, as_of=as_of, generator=generator,
    )
