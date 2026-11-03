"""Conservative source-bound lens candidates for RCT research.

NOT semantic authority. Only exact finite patterns produce cited source claims.
PackSpec completeness and source authenticity remain UNKNOWN.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any

from store import canonical_bytes, digest

SCHEMA = "rct.source-lens/v0.6"
PATTERNS = {
    "head": r"\bbody\s+has\s+(?:three|3)\s+(?:main\s+)?(?:parts|regions)\s*:\s*head\s*,\s*trunk\s*,?\s*(?:and\s+)?limbs\b",
    "trunk": r"\bbody\s+has\s+(?:three|3)\s+(?:main\s+)?(?:parts|regions)\s*:\s*head\s*,\s*trunk\s*,?\s*(?:and\s+)?limbs\b",
    "limbs": r"\bbody\s+has\s+(?:three|3)\s+(?:main\s+)?(?:parts|regions)\s*:\s*head\s*,\s*trunk\s*,?\s*(?:and\s+)?limbs\b",
    "heart-location": r"\bheart\s+is\s+located\s+in\s+(?:the\s+)?thorax\b",
    "perspective": r"\bparallel\s+edges\s+(?:in\s+perspective\s+)?(?:appear\s+to\s+)?converge\s+(?:toward|at)\s+(?:a\s+)?vanishing\s+point\b",
    "occlusion": r"\bfront\s+surface\s+(?:can\s+)?hide\s+(?:a\s+)?rear\s+surface\b",
}

def compile_lens(source: str, *, lens_id: str, purpose: str,
                 required: tuple[str, ...],
                 permitted_omissions: tuple[str, ...] = ()) -> dict[str, Any]:
    if not isinstance(source, str) or not source.strip() or len(source) > 100000:
        raise ValueError("Invalid source length")
    if not lens_id or not purpose or not required or len(set(required)) != len(required):
        raise ValueError("Lens id, purpose, unique requirements required")
    if any(item not in PATTERNS for item in (*required, *permitted_omissions)):
        raise ValueError("Unsupported distinction")
    if set(required) & set(permitted_omissions):
        raise ValueError("Required distinction cannot be omitted")
    claims = []
    for distinction in required:
        for match in re.finditer(PATTERNS[distinction], source, flags=re.I):
            preceding = source[max(0, match.start() - 40):match.start()].lower()
            if re.search(r"\b(?:not|false|incorrect)\s*[:.\-]?\s*$", preceding):
                continue
            quote = source[match.start():match.end()]
            claims.append({"distinction": distinction, "start": match.start(),
                           "end": match.end(), "quote_sha256": sha256(quote.encode()).hexdigest(),
                           "quote": quote, "status": "UNVERIFIED_SOURCE_CLAIM"})
    unresolved = sorted(set(required) - {c["distinction"] for c in claims})
    result = {"schema": SCHEMA, "lens_id": lens_id, "purpose": purpose,
              "source_sha256": sha256(source.encode()).hexdigest(),
              "required": list(required), "permitted_omissions": list(permitted_omissions),
              "candidate_claims": claims, "unresolved": unresolved,
              "local_coverage": "UNKNOWN" if unresolved else "DECLARED_CLAIMS_PRESENT",
              "qualityrag_admission": "INCONCLUSIVE", "source_authenticity": "UNVERIFIED",
              "packspec_completeness": "UNKNOWN", "grammar": "FINITE_PATTERNS_ONLY"}
    result["fingerprint"] = digest(result)
    return result

def persist_lens(store: Any, *, lens: dict[str, Any], source_id: str,
                 revision: str, packspec_digest: str) -> dict[str, str]:
    if not source_id or not revision or not packspec_digest:
        raise ValueError("Source, revision and PackSpec digest required")
    data = dict(lens)
    fingerprint = data.pop("fingerprint", None)
    if (fingerprint != digest(data) or data.get("schema") != SCHEMA
            or data.get("qualityrag_admission") != "INCONCLUSIVE"
            or data.get("source_authenticity") != "UNVERIFIED"):
        raise ValueError("Untrusted or tampered candidate")
    oid = f"rct:lens:{lens['lens_id']}"
    checks = [{"status": "UNKNOWN", "reason": "Source authenticity unverified"},
              {"status": "UNKNOWN", "reason": "PackSpec completeness unverified"}]
    reason = "Trusted verifier binding not implemented"
    receipt = {"object_id": oid, "revision": revision, "packspec_digest": packspec_digest,
               "checks": checks, "verdict": "INCONCLUSIVE", "reason": reason}
    with store.db:
        existing = store.db.execute(
            "SELECT source_sha256 FROM source_versions WHERE source_id=? AND revision=?",
            (source_id, revision)).fetchone()
        if existing is not None and existing[0] != data["source_sha256"]:
            raise ValueError("Source identity/revision already bound to different digest")
        if existing is None:
            store.db.execute("INSERT INTO source_versions VALUES (?,?,?,?)",
                             (source_id, revision, data["source_sha256"],
                              canonical_bytes({"assurance": "UNVERIFIED_SOURCE", "grammar": SCHEMA}).decode()))
        store.db.execute("INSERT INTO semantic_versions VALUES (?,?,?,?,?,?,?)",
                         (oid, revision, source_id, revision, "GRAMMAR_CANDIDATE",
                          canonical_bytes(lens).decode(), digest(lens)))
        store.db.execute("INSERT INTO admission_receipts VALUES (?,?,?,?,?,?,?)",
                         (digest(receipt), oid, revision, packspec_digest,
                          "INCONCLUSIVE", reason, canonical_bytes(checks).decode()))
    return {"object_id": oid, "revision": revision,
            "admission": "INCONCLUSIVE", "receipt_hash": digest(receipt)}
