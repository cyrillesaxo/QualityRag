"""Reversible multiscale graph reference frame, NOT native FF-RCT.

Separates full-fidelity source payload from predicate/source summary layers.
The payload is losslessly compressed using zlib, never by dropping evidence.
Structural summaries can be navigated; decode always verifies source digest.
This reference establishes a reconstruction seam, not the FF-RCT codec claim.
"""
from __future__ import annotations

import base64
import json
import zlib
from hashlib import sha256

from rct_grammar import _validate
from store import canonical_bytes, digest

SCHEMA = "rct.multiscale-reference-frame/v2"
MAX_SOURCE_BYTES = 2_000_000
MAX_COMPRESSED_BYTES = MAX_SOURCE_BYTES + 10_000


def encode_reference_frame(source: dict, *, level: int = 6) -> dict:
    facts = _validate(source)
    if type(level) is not int or not 0 <= level <= 9:
        raise ValueError("Invalid compression level")
    raw = canonical_bytes(source)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds reference-frame byte budget")
    by_predicate, by_origin = {}, {}
    for f in facts:
        by_predicate.setdefault(f["predicate"], []).append(f["id"])
        by_origin.setdefault(f["source_ref"], []).append(f["id"])
    compressed = zlib.compress(raw, level)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError("Compressed frame exceeds byte budget")
    frame = {
        "schema": SCHEMA,
        "compression": "zlib-lossless-reference-NOT-FF-RCT",
        "encoding": "base64url",
        "source_sha256": sha256(raw).hexdigest(),
        "original_bytes": len(raw),
        "compressed_bytes": len(compressed),
        "fact_count": len(facts),
        "levels": {
            "L0": {"fact_count": len(facts), "source_sha256": sha256(raw).hexdigest()},
            "L1_predicates": {k: sorted(v) for k, v in sorted(by_predicate.items())},
            "L1_sources": {k: sorted(v) for k, v in sorted(by_origin.items())},
        },
        "data": base64.urlsafe_b64encode(compressed).decode("ascii"),
        "fidelity": "EXACT_CANONICAL_JSON_RECONSTRUCTION",
        "qualityrag_admission": "INCONCLUSIVE",
    }
    frame["fingerprint"] = digest(frame)
    return frame


def decode_reference_frame(frame: dict) -> dict:
    if not isinstance(frame, dict):
        raise ValueError("Frame required")
    f = dict(frame)
    fingerprint = f.pop("fingerprint", None)
    if (fingerprint != digest(f) or f.get("schema") != SCHEMA
            or f.get("compression") != "zlib-lossless-reference-NOT-FF-RCT"
            or f.get("fidelity") != "EXACT_CANONICAL_JSON_RECONSTRUCTION"
            or f.get("qualityrag_admission") != "INCONCLUSIVE"):
        raise ValueError("Tampered or unsupported reference frame")
    n = frame.get("original_bytes")
    compressed_n = frame.get("compressed_bytes")
    if (type(n) is not int or not 1 <= n <= MAX_SOURCE_BYTES
            or type(compressed_n) is not int
            or not 1 <= compressed_n <= MAX_COMPRESSED_BYTES
            or not isinstance(frame.get("data"), str)
            or len(frame["data"]) > 4 * ((MAX_COMPRESSED_BYTES + 2) // 3)):
        raise ValueError("Unbounded reference frame")
    try:
        payload = base64.b64decode(frame["data"], altchars=b"-_", validate=True)
        if len(payload) != compressed_n:
            raise ValueError("Compressed-size mismatch")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(payload, n + 1)
        if (len(raw) != n or not decoder.eof or decoder.unused_data
                or decoder.unconsumed_tail or decoder.flush()):
            raise ValueError("Truncated or excess frame data")
        if sha256(raw).hexdigest() != frame["source_sha256"]:
            raise ValueError("Reconstruction digest mismatch")
        source = json.loads(raw)
        facts = _validate(source)
    except (KeyError, TypeError, zlib.error, ValueError, UnicodeError,
            json.JSONDecodeError) as exc:
        raise ValueError("Reference frame reconstruction failed") from exc
    # Summaries are checked, not trusted as alternative ground truth.
    if (canonical_bytes(source) != raw
            or len(facts) != frame["fact_count"]):
        raise ValueError("Noncanonical or incomplete reconstruction")
    expected = encode_reference_frame(source)
    if expected["levels"] != frame["levels"]:
        raise ValueError("Tampered multiscale structural index")
    return source
