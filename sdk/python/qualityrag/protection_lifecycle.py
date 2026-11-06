"""In-process policy lifecycle for synthetic purpose-bound protection.

The *trusted registry service* owns the policy state. Do not accept a registry
instance, active version, or revocation update from an untrusted request.
This in-memory example does not synchronize across processes or survive restarts.
"""
from __future__ import annotations

import threading

from .protection import ProtectionDenied


class InMemoryPolicyAuthority:
    """Thread-safe demonstration of active policy version and revocation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active: dict[tuple[str, str], int] = {}

    def publish(self, *, tenant: str, policy_id: str, version: int) -> None:
        if (not isinstance(tenant, str) or not tenant
                or not isinstance(policy_id, str) or not policy_id
                or type(version) is not int or version < 1):
            raise ProtectionDenied("INVALID_POLICY_VERSION")
        with self._lock:
            key = (tenant, policy_id)
            previous = self._active.get(key, 0)
            if version <= previous:
                raise ProtectionDenied("NON_MONOTONIC_POLICY_VERSION")
            self._active[key] = version

    def revoke(self, *, tenant: str, policy_id: str) -> None:
        with self._lock:
            self._active.pop((tenant, policy_id), None)

    def require_active(self, *, tenant: str, policy_id: str, version: int) -> None:
        with self._lock:
            if self._active.get((tenant, policy_id)) != version:
                raise ProtectionDenied("POLICY_NOT_ACTIVE")
