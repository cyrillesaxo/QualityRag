"""Experimental server-held authorization receipts with opaque request handles.

This wrapper prevents the model-facing API from returning the signed receipt,
source reference or release metadata. No HTTP, PANs, payment operations, or
production authentication are implemented.
"""
from __future__ import annotations

from copy import deepcopy
import secrets
import threading
from typing import Any

from .protection import ProtectionDenied
from .protection_disclosure import DryRunDisclosureGateway
from .protection_service import ProtectionService


class InMemoryReceiptRegistry:
    """Trusted, bounded single-process receipt store. Not distributed storage."""

    def __init__(self, *, max_pending: int = 1024):
        if type(max_pending) is not int or max_pending < 1:
            raise ProtectionDenied("INVALID_RECEIPT_CAPACITY")
        self._max_pending = max_pending
        self._receipts: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def put(self, envelope: dict[str, Any], *, now: int) -> str:
        receipt = envelope.get("receipt") if isinstance(envelope, dict) else None
        if (not isinstance(receipt, dict)
            or type(receipt.get("expires_at")) is not int
            or type(now) is not int):
            raise ProtectionDenied("INVALID_RECEIPT")
        with self._lock:
            self._receipts = {
                key: item for key, item in self._receipts.items()
                if item["receipt"]["expires_at"] >= now
            }
            if len(self._receipts) >= self._max_pending:
                raise ProtectionDenied("RECEIPT_CAPACITY_REACHED")
            handle = "req_" + secrets.token_hex(24)
            self._receipts[handle] = deepcopy(envelope)
            return handle

    def read(self, handle: str, *, now: int) -> dict[str, Any]:
        if not isinstance(handle, str) or not handle.startswith("req_"):
            raise ProtectionDenied("UNKNOWN_REQUEST")
        if type(now) is not int:
            raise ProtectionDenied("INVALID_TIME")
        with self._lock:
            envelope = self._receipts.get(handle)
            if not envelope or envelope["receipt"]["expires_at"] < now:
                self._receipts.pop(handle, None)
                raise ProtectionDenied("UNKNOWN_REQUEST")
            return deepcopy(envelope)

    def discard(self, handle: str) -> None:
        with self._lock:
            self._receipts.pop(handle, None)


class OpaqueDisclosureFacade:
    """Model-facing API in a synthetic trust boundary.

    Only the minimal authorized view and an opaque handle leave prepare().
    The receipt, policy revision, subject and source reference stay inside
    this trusted process. The caller cannot provide a receipt or a sink.
    """

    def __init__(self, *, service: ProtectionService,
                 gateway: DryRunDisclosureGateway,
                 registry: InMemoryReceiptRegistry):
        if (not isinstance(service, ProtectionService)
            or not isinstance(gateway, DryRunDisclosureGateway)
            or not isinstance(registry, InMemoryReceiptRegistry)):
            raise ProtectionDenied("INVALID_FACADE_CONFIG")
        if gateway._service is not service:
            raise ProtectionDenied("GATEWAY_SERVICE_MISMATCH")
        self._service = service
        self._gateway = gateway
        self._registry = registry

    def prepare_payment(self, *, assertion: dict[str, Any],
                        payment_reference: str,
                        contract_attestation: dict[str, Any],
                        purpose: str, destination: str,
                        now: int | None = None) -> dict[str, Any]:
        # Ingress caller controls a reference, not metadata attributes.
        envelope = self._service.issue_payment_metadata(
            assertion=assertion, payment_reference=payment_reference,
            contract_attestation=contract_attestation, purpose=purpose,
            destination=destination, now=now)
        issued_at = envelope["receipt"]["issued_at"]
        handle = self._registry.put(envelope, now=issued_at)
        return {
            "request_handle": handle,
            "view": deepcopy(envelope["receipt"]["protected_view"]["view"]),
        }

    def deliver(self, *, assertion: dict[str, Any], request_handle: str,
                purpose: str, destination: str,
                now: int) -> dict[str, str]:
        # Only server-held receipts are accepted. The gateway independently
        # revalidates authenticated identity, grants, policy and source access.
        envelope = self._registry.read(request_handle, now=now)
        try:
            result = self._gateway.deliver(
                assertion=assertion, envelope=envelope, purpose=purpose,
                destination=destination, now=now)
        except ProtectionDenied as exc:
            # A failed sink attempt has already consumed its receipt.
            if str(exc) in ("SIMULATED_DELIVERY_FAILED", "REPLAY_DENIED"):
                self._registry.discard(request_handle)
            raise
        self._registry.discard(request_handle)
        return result
