"""Adapter for preserving APX HCR/RCOC results without re-running their algorithms.

Untrusted input and reported digests remain UNVERIFIED_EXTERNAL_RESULT.
A bounded HCR diagnosis or RCOC diff is never a PackSpec ADMIT verdict.
"""
from __future__ import annotations

import json
from typing import Any
from store import digest

SCHEMAS = {
    "HCR": "apx.hcr/v0.1",
    "RCOC": "apx.rcoc-semantic-diff/v0.1",
}
HCR_IDENTIFIABILITY = {
    "NO_REGISTERED_MODEL", "IDENTIFIED_WITHIN_REGISTRY",
    "PARTIAL_EQUIVALENCE_CLASS", "SINGLE_COMPATIBLE_UNCONFIRMED",
    "EMPTY_FIBER_WITHIN_REGISTRY",
}
RCOC_STATUSES = {
    "INCOMPARABLE", "REVIEW_REQUIRED",
    "IMPROVED_WITHIN_OBSERVED_RECEIPTS",
    "NO_MATERIAL_SEMANTIC_MOVEMENT_ESTABLISHED",
}


class APXReceiptError(ValueError):
    pass


def validate_receipt(engine: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate outer APX contract only, not underlying evidence or truth."""
    if engine not in SCHEMAS or not isinstance(receipt, dict):
        raise APXReceiptError("Unsupported APX engine/receipt")
    if receipt.get("schema") != SCHEMAS[engine]:
        raise APXReceiptError("APX schema mismatch")
    if not isinstance(receipt.get("boundary"), str) or not receipt["boundary"].strip():
        raise APXReceiptError("APX receipt missing epistemic boundary")
    if engine == "HCR":
        if receipt.get("engine") != "HCR":
            raise APXReceiptError("HCR engine identity mismatch")
        admission = receipt.get("admission")
        identification = receipt.get("identifiability")
        registry = receipt.get("registry")
        if (not isinstance(admission, dict)
            or admission.get("status") not in ("BOUNDED_DIAGNOSIS", "INCONCLUSIVE")
            or not isinstance(identification, dict)
            or identification.get("status") not in HCR_IDENTIFIABILITY
            or not isinstance(registry, dict)
            or not isinstance(registry.get("digest"), str)
            or not registry["digest"]):
            raise APXReceiptError("Malformed bounded HCR admission")
        if admission["status"] == "BOUNDED_DIAGNOSIS" and (
            identification["status"] != "IDENTIFIED_WITHIN_REGISTRY"
            or registry["digest"] != admission.get("registry_digest")
        ):
            raise APXReceiptError("HCR bounded diagnosis lacks registered identity")
        outcome = admission["status"]
        refs = {"registered_family": registry["digest"]}
    else:
        if receipt.get("status") not in RCOC_STATUSES:
            raise APXReceiptError("Unsupported RCOC diff status")
        admission = receipt.get("admission")
        if (receipt["status"] != "INCOMPARABLE"
                and (not isinstance(admission, dict)
                     or admission.get("status") not in ("BOUNDED_DIFF", "INCONCLUSIVE"))):
            raise APXReceiptError("RCOC missing bounded diff admission")
        if (receipt["status"] in ("REVIEW_REQUIRED", "INCOMPARABLE")
                and isinstance(admission, dict)
                and admission.get("status") == "BOUNDED_DIFF"):
            raise APXReceiptError("RCOC review/incomparable cannot claim bounded admission")
        outcome = receipt["status"]
        refs = {
            "before_revision": (receipt.get("before") or {}).get("revision"),
            "after_revision": (receipt.get("after") or {}).get("revision"),
        }
    return {
        "engine": engine,
        "schema": receipt["schema"],
        "outcome": outcome,
        "source_digests": refs,
        "authority": "UNVERIFIED_EXTERNAL_RESULT",
        "admission": "INCONCLUSIVE",
    }


def record_apx_receipt(store: Any, *, object_id: str, revision: str,
                       engine: str, receipt: dict[str, Any]) -> dict[str, Any]:
    classification = validate_receipt(engine, receipt)
    h = digest({"engine": engine, "object_id": object_id, "revision": revision,
                "receipt": receipt})
    canonical = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False)
    with store.db:
        store.db.execute(
            "INSERT INTO apx_receipts "
            "(receipt_sha256, object_id, revision, engine, schema_id, "
            "source_digests_json, receipt_json, verification) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (h, object_id, revision, engine, classification["schema"],
             canonical(classification["source_digests"]), canonical(receipt),
             "UNVERIFIED_EXTERNAL_RESULT"))
    return {
        **classification,
        "receipt_sha256": h,
    }
