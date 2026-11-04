"""Shared bounded serialization; source text is data, never executable code."""
from hashlib import sha256
import json
import re

MAX_BYTES = 524288
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
HEX = re.compile(r"^[0-9a-f]{64}$")


def identity(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid bounded identifier")
    return value


def canonical(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("Artifact exceeds byte budget")
    return raw


def fingerprint(value):
    return sha256(canonical(value)).hexdigest()


def strict_json(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("Invalid JSON byte budget")
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("Duplicate JSON key")
            out[k] = v
        return out
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite number")))
    except (RecursionError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed bounded JSON") from exc
