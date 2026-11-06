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
