"""Experimental open-core purpose-bound disclosure gate.

No PAN collection, encryption, token vault, detokenization, or PCI certification.
Only source-provided, already-safe attributes and opaque references are accepted.
Unknown classifications and unspecified permissions fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

SCHEMA = "qualityrag.protection/v0.1"
_ALLOWED = frozenset({"public", "internal", "restricted", "pci"})
_PAN_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_TOKEN = re.compile(r"^ref_[a-zA-Z0-9_-]{12,128}$")
_SAFE_ATTRIBUTES = frozenset({"card_brand", "last_four", "expiry_valid", "same_instrument", "payment_eligible"})

class ProtectionDenied(ValueError):
    """Policy denial; messages must never include source values."""


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant: str
    purposes: frozenset[str]

    def __post_init__(self):
        if not self.subject or not self.tenant or not self.purposes:
            raise ProtectionDenied("INVALID_PRINCIPAL")


def _safe_string(value: Any) -> bool:
    return isinstance(value, str) and not _PAN_CANDIDATE.search(value)


def protect(record: dict[str, Any], contract: dict[str, Any], principal: Principal, *,
            purpose: str, destination: str) -> dict[str, Any]:
    """Produce a minimal approved view. Contract and derived attributes MUST come
    from trusted resource infrastructure, not a model or an untrusted document.
    Not a generic detector for free text; ingest must classify it separately.
    """
    if not isinstance(record, dict) or not isinstance(contract, dict):
        raise ProtectionDenied("INVALID_INPUT")
    if purpose not in principal.purposes:
        raise ProtectionDenied("PURPOSE_NOT_GRANTED")
    if contract.get("schema") != SCHEMA or contract.get("tenant") != principal.tenant:
        raise ProtectionDenied("UNVERIFIED_CONTRACT")
    if not contract.get("authenticated", False):
        raise ProtectionDenied("UNVERIFIED_CONTRACT")
    fields = contract.get("fields")
    if not isinstance(fields, dict) or set(record) != set(fields):
        raise ProtectionDenied("UNCLASSIFIED_FIELD")
    result: dict[str, Any] = {}
    for name, value in record.items():
        spec = fields[name]
        if not isinstance(name, str) or not isinstance(spec, dict):
            raise ProtectionDenied("INVALID_FIELD_CONTRACT")
        classification = spec.get("classification")
        if classification not in _ALLOWED:
            raise ProtectionDenied("UNKNOWN_CLASSIFICATION")
        grants = spec.get("grants")
        if not isinstance(grants, list) or not any(
            isinstance(g, dict) and g.get("purpose") == purpose
            and g.get("destination") == destination
            and g.get("operation") == "read"
            for g in grants
        ):
            continue
        mode = spec.get("mode")
        if classification in ("restricted", "pci"):
            if mode == "reference":
                if not _safe_string(value) or not _TOKEN.fullmatch(value):
                    raise ProtectionDenied("UNSAFE_REFERENCE")
                result[name] = value
            elif mode == "derived":
                if name not in _SAFE_ATTRIBUTES or type(value) not in (str, bool):
                    raise ProtectionDenied("INVALID_DERIVED_ATTRIBUTE")
                if name == "last_four" and (not isinstance(value, str) or
                                              not re.fullmatch(r"\d{4}", value)):
                    raise ProtectionDenied("INVALID_DERIVED_ATTRIBUTE")
                if name in ("expiry_valid", "same_instrument", "payment_eligible") and type(value) is not bool:
                    raise ProtectionDenied("INVALID_DERIVED_ATTRIBUTE")
                if not _safe_string(value):
                    raise ProtectionDenied("UNSAFE_DERIVED_ATTRIBUTE")
                result[name] = value
            else:
                raise ProtectionDenied("SENSITIVE_PLAINTEXT_DENIED")
        elif mode == "plain" and _safe_string(value) and type(value) in (str, bool):
            result[name] = value
        else:
            raise ProtectionDenied("UNSAFE_VALUE")
    return {"schema": SCHEMA, "tenant": principal.tenant, "purpose": purpose,
            "destination": destination, "subject": principal.subject, "view": result}


def authorize_release(view: dict[str, Any], principal: Principal, *,
                      destination: str, purpose: str, operation: str = "read") -> dict[str, Any]:
    """Reference-only release check. NO detokenization, transfers or external effects."""
    if operation != "read" or not isinstance(view, dict):
        raise ProtectionDenied("OPERATION_DENIED")
    if (view.get("schema") != SCHEMA or view.get("tenant") != principal.tenant
        or view.get("subject") != principal.subject
        or view.get("destination") != destination
        or view.get("purpose") != purpose or purpose not in principal.purposes):
        raise ProtectionDenied("RELEASE_DENIED")
    data = view.get("view")
    if not isinstance(data, dict):
        raise ProtectionDenied("INVALID_VIEW")
    if any(not (type(v) is bool or _safe_string(v)) for v in data.values()):
        raise ProtectionDenied("UNSAFE_RELEASE")
    return {"decision": "ALLOW_REFERENCE_ONLY", "destination": destination,
            "operation": operation, "view": dict(data)}
