"""Provider-neutral interface for already-protected payment metadata.

This module deliberately has NO reveal, decrypt, or detokenize operation.
Any real payment operation belongs to a separate, independently authorized
service. The included fake adapter stores only synthetic metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import re

from .protection import ProtectionDenied

_REFERENCE = re.compile(r"^ref_[A-Za-z0-9_-]{12,128}$")
_BRANDS = frozenset({"visa", "mastercard", "amex", "discover", "other"})


@dataclass(frozen=True)
class ProtectedPayment:
    reference: str
    tenant: str
    card_brand: str
    last_four: str
    expiry_valid: bool

    def __post_init__(self) -> None:
        if (not isinstance(self.reference, str)
                or not _REFERENCE.fullmatch(self.reference)
                or not isinstance(self.tenant, str) or not self.tenant
                or self.card_brand not in _BRANDS
                or not isinstance(self.last_four, str)
                or not re.fullmatch(r"\d{4}", self.last_four)
                or type(self.expiry_valid) is not bool):
            raise ProtectionDenied("INVALID_PROTECTED_PAYMENT")

    def attributes(self) -> dict[str, str | bool]:
        """Minimal view; never contains a PAN."""
        return {"payment_ref": self.reference, "card_brand": self.card_brand,
                "last_four": self.last_four, "expiry_valid": self.expiry_valid}


class ProtectedMetadataProvider(Protocol):
    """Adapter API implemented by a trusted, independently authenticated service."""

    def get_protected_payment(self, *, tenant: str, reference: str) -> ProtectedPayment:
        """Retrieve permitted metadata only. No raw credentials or secret keys."""


class SyntheticMetadataProvider:
    """In-memory demo with synthetic protected data ONLY. Not a vault."""

    def __init__(self, payments: list[ProtectedPayment]) -> None:
        self._items: dict[tuple[str, str], ProtectedPayment] = {}
        for item in payments:
            key = (item.tenant, item.reference)
            if key in self._items:
                raise ProtectionDenied("DUPLICATE_REFERENCE")
            self._items[key] = item

    def get_protected_payment(self, *, tenant: str, reference: str) -> ProtectedPayment:
        if not isinstance(tenant, str) or not isinstance(reference, str):
            raise ProtectionDenied("NOT_FOUND")
        item = self._items.get((tenant, reference))
        if item is None:
            raise ProtectionDenied("NOT_FOUND")
        return item


class AuthorizedMetadataProvider(Protocol):
    """Trusted provider must independently authorize access to each reference."""

    def get_authorized_payment(self, *, tenant: str, subject: str,
                               purpose: str, reference: str) -> ProtectedPayment:
        """Return a tenant-bound payment only for the allowed subject/purpose."""


class SyntheticAuthorizedMetadataProvider:
    """Explicit object-level access grants for synthetic fixture records only.

    This is a standalone simulation: no cryptographic identity, vault or
    durable authorization. The trusted service, not the client, owns grants.
    """

    def __init__(self, payments: list[ProtectedPayment],
                 access: dict[tuple[str, str], set[tuple[str, str]]]) -> None:
        self._payments = SyntheticMetadataProvider(payments)
        if not isinstance(access, dict):
            raise ProtectionDenied("INVALID_METADATA_GRANTS")
        self._access: dict[tuple[str, str], frozenset[tuple[str, str]]] = {}
        for key, grants in access.items():
            if (not isinstance(key, tuple) or len(key) != 2 or
                not all(isinstance(x, str) and x for x in key) or
                not isinstance(grants, set) or
                not all(isinstance(g, tuple) and len(g) == 2 and
                        all(isinstance(x, str) and x for x in g) for g in grants)):
                raise ProtectionDenied("INVALID_METADATA_GRANTS")
            self._access[key] = frozenset(grants)

    def revoke_synthetic_access(self, *, tenant: str, reference: str,
                                subject: str, purpose: str) -> None:
        """Test-only revocation; not atomic with a concurrent service release."""
        key = (tenant, reference)
        self._access[key] = self._access.get(key, frozenset()).difference(
            {(subject, purpose)})

    def replace_synthetic_payment(self, payment: ProtectedPayment) -> None:
        """Test-only simulation of authoritative source attribute changes."""
        key = (payment.tenant, payment.reference)
        if key not in self._payments._items:
            raise ProtectionDenied("NOT_FOUND")
        self._payments._items[key] = payment

    def get_authorized_payment(self, *, tenant: str, subject: str,
                               purpose: str, reference: str) -> ProtectedPayment:
        if (not isinstance(subject, str) or not subject or
            not isinstance(purpose, str) or not purpose or
            (subject, purpose) not in self._access.get((tenant, reference), frozenset())):
            raise ProtectionDenied("METADATA_ACCESS_DENIED")
        item = self._payments.get_protected_payment(tenant=tenant, reference=reference)
        if item.tenant != tenant or item.reference != reference:
            raise ProtectionDenied("METADATA_SOURCE_MISMATCH")
        return item
