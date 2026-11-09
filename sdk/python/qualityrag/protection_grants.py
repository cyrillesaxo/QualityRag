"""Server-owned workload allowlist for the synthetic protection service.

This is a static, in-process policy fixture. An IdP assertion authenticates the
workload; the resource service *independently* authorizes its tenant, subject,
purpose and destination. This module does not implement RBAC provisioning,
federation or production access control.
"""
from __future__ import annotations
from dataclasses import dataclass

from .protection import Principal, ProtectionDenied


@dataclass(frozen=True)
class WorkloadGrant:
    tenant: str
    subject: str
    purpose: str
    destination: str

    def __post_init__(self) -> None:
        if not all(isinstance(v, str) and v for v in (
            self.tenant, self.subject, self.purpose, self.destination
        )):
            raise ProtectionDenied("INVALID_WORKLOAD_GRANT")


class StaticWorkloadGrants:
    """Constructed only by trusted service configuration, never user input."""
    def __init__(self, grants: list[WorkloadGrant]) -> None:
        if not isinstance(grants, list) or not all(
                isinstance(g, WorkloadGrant) for g in grants):
            raise ProtectionDenied("INVALID_WORKLOAD_GRANT")
        self._grants = frozenset(grants)

    def require(self, principal: Principal, *, purpose: str,
                destination: str) -> None:
        if (purpose not in principal.purposes
                or WorkloadGrant(principal.tenant, principal.subject,
                                 purpose, destination) not in self._grants):
            raise ProtectionDenied("WORKLOAD_NOT_AUTHORIZED")
