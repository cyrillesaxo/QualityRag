"""Pinned local JSON Schema catalog, with no remote schema resolution.

Schemas check shape. Runtime validators also enforce byte budgets, fingerprints,
field bijection, endpoint typing and authorization. Shape is never admission.
"""
import json
from pathlib import Path

from .common import canonical

CATALOG = Path(__file__).with_name("schemas")
NAMES = frozenset({"grammar", "source", "payload", "transform", "packspec", "verdict", "receipt", "operator-ast", "reviewed-activation", "observation-graph"})


def validate(name, value):
    if name not in NAMES:
        raise ValueError("Unknown schema")
    # Lazy dependency: a missing validator is an explicit error, never PASS.
    from jsonschema import Draft202012Validator
    canonical(value)
    schema = json.loads((CATALOG / (name + ".json")).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)
    return value
