"""Reference-only dry-run disclosure gateway for QualityRAG Protect.

No sockets, HTTP, payment operations or real detokenization. The gateway
accepts only service-configured destinations and simulated sinks, never
user-provided URLs or untrusted callback objects. External delivery requires
a separately reviewed, authenticated adapter.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from .protection import ProtectionDenied
from .protection_service import ProtectionService


class ReferenceSink(Protocol):
    """Trusted test sink. Implementations must not detokenize."""
    def accept(self, view: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class DisclosureRoute:
    destination: str
    sink: ReferenceSink

    def __post_init__(self):
        if not isinstance(self.destination, str) or not self.destination:
            raise ProtectionDenied("INVALID_DESTINATION")
        if not callable(getattr(self.sink, "accept", None)):
            raise ProtectionDenied("INVALID_SINK")


class MemoryReferenceSink:
    """Fake destination for regression tests. No external side effects."""
    def __init__(self):
        self.received: list[dict[str, Any]] = []

    def accept(self, view: dict[str, Any]) -> None:
        self.received.append(deepcopy(view))


class DryRunDisclosureGateway:
    """Consume a signed receipt before delivering to a configured fake sink.

    At-most-one authorization CLAIM; not exactly-once delivery. If the sink
    fails after the claim, retries need a *new* authorization. Revocation
    between commit and sink execution is not atomic with actual delivery.
    """

    def __init__(self, *, service: ProtectionService, routes: list[DisclosureRoute]):
        if not isinstance(service, ProtectionService) or not isinstance(routes, list):
            raise ProtectionDenied("INVALID_GATEWAY_CONFIG")
        if not routes or not all(isinstance(r, DisclosureRoute) for r in routes):
            raise ProtectionDenied("INVALID_GATEWAY_CONFIG")
        dests = [r.destination for r in routes]
        if len(dests) != len(set(dests)):
            raise ProtectionDenied("DUPLICATE_DESTINATION")
        self._service = service
        self._routes = {r.destination: r.sink for r in routes}

    def deliver(self, *, assertion: dict[str, Any], envelope: dict[str, Any],
                purpose: str, destination: str,
                now: int | None = None) -> dict[str, str]:
        if not isinstance(destination, str) or destination not in self._routes:
            raise ProtectionDenied("DESTINATION_NOT_CONFIGURED")
        # All identity/grant/signature/audience/policy/replay checks happen
        # *before* the sink sees anything. Denied attempts never call sink.
        release = self._service.release(
            assertion=assertion, envelope=envelope, purpose=purpose,
            destination=destination, now=now)
        if release.get("decision") != "ALLOW_REFERENCE_ONLY":
            raise ProtectionDenied("UNSUPPORTED_RELEASE")
        try:
            self._routes[destination].accept(deepcopy(release["view"]))
        except Exception:
            # Do not propagate the simulated sink exception or sensitive detail.
            raise ProtectionDenied("SIMULATED_DELIVERY_FAILED") from None
        return {"status": "SIMULATED_DELIVERY_ACCEPTED", "destination": destination}
