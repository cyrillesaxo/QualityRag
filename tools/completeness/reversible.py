"""Reversible source accounting; semantic completeness is NEVER inferred from round-trip fidelity."""
import base64
import hashlib
from dataclasses import dataclass


class ConservationError(ValueError):
    pass


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    payload_b64: str
    role: str


@dataclass(frozen=True)
class UniversePackSpec:
    digest: str
    size: int
    codec: str = "1"


@dataclass(frozen=True)
class PackSpecProjection:
    digest: str
    admitted: tuple[Span, ...]


@dataclass(frozen=True)
class DiffPackSpec:
    digest: str
    residual: tuple[Span, ...]
    semantic_verdict: str = "UNKNOWN"


def _hash(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def ingest(source: bytes, admitted_ranges) -> tuple[UniversePackSpec, PackSpecProjection, DiffPackSpec]:
    """Ranges are half-open BYTE offsets; remaining bytes become DiffPackSpec residual."""
    if not isinstance(source, bytes):
        raise TypeError("Source must be bytes")
    n = len(source)
    admitted, residual, pos = [], [], 0

    def add(out, start, end, role):
        if start < end:
            out.append(Span(start, end, base64.b64encode(source[start:end]).decode("ascii"), role))

    for start, end in sorted(admitted_ranges):
        if (type(start) is not int or type(end) is not int
                or start < pos or end <= start or end > n):
            raise ConservationError("Invalid, overlapping or out-of-bounds span")
        add(residual, pos, start, "residual")
        add(admitted, start, end, "admitted")
        pos = end
    add(residual, pos, n, "residual")
    digest = _hash(source)
    result = (
        UniversePackSpec(digest, n),
        PackSpecProjection(digest, tuple(admitted)),
        DiffPackSpec(digest, tuple(residual)),
    )
    if reconstruct(*result) != source:
        raise ConservationError("Round-trip failure")
    return result


def reconstruct(universe: UniversePackSpec, projection: PackSpecProjection, diff: DiffPackSpec) -> bytes:
    if universe.codec != "1":
        raise ConservationError("Unknown codec")
    if universe.digest != projection.digest or universe.digest != diff.digest:
        raise ConservationError("Mixed source versions")
    spans = sorted((*projection.admitted, *diff.residual), key=lambda s: (s.start, s.end))
    pos, parts = 0, []
    for span in spans:
        if (span.start != pos or span.end <= span.start
                or (span.role == "admitted" and span not in projection.admitted)
                or (span.role == "residual" and span not in diff.residual)
                or span.role not in ("admitted", "residual")):
            raise ConservationError("Gap, overlap or invalid classification")
        try:
            payload = base64.b64decode(span.payload_b64, validate=True)
        except Exception as exc:
            raise ConservationError("Invalid span encoding") from exc
        if len(payload) != span.end - span.start:
            raise ConservationError("Span length mismatch")
        parts.append(payload)
        pos = span.end
    result = b"".join(parts)
    if pos != universe.size or _hash(result) != universe.digest:
        raise ConservationError("Incomplete or altered reconstruction")
    return result


def completeness_status(universe, projection, diff):
    reconstruct(universe, projection, diff)
    if diff.semantic_verdict != "UNKNOWN":
        raise ConservationError("Independent semantic validation required")
    return {
        "source_integrity": "PASS",
        "admitted_bytes": sum(s.end - s.start for s in projection.admitted),
        "residual_bytes": sum(s.end - s.start for s in diff.residual),
        "semantic_completeness": "UNKNOWN",
        "decision_authorization": "NOT_ESTABLISHED",
    }
