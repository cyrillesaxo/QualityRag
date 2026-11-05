"""Bounded activation-grammar research runtime.

This module evaluates explicitly declared task observations against a small
PackSpec-style contract. It is NOT a video codec, semantic truth checker, or
production PackSpec interpreter. Source values are caller-supplied claims.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

SCHEMA = "qualityrag.activation-grammar/v0.1"
CONTRACT_SCHEMA = "qualityrag.activation-contract/v0.1"
MAX_REGIMES = 32
MAX_FIELDS = 128
MAX_OPERATORS = 32
MAX_TEXT = 512
OPERATORS = {"PRESERVE", "TRANSITION", "ACTIVATE", "VERIFY", "FALLBACK"}
# Exact keys each operator may carry; a misspelled key must fail, not silently default.
OPERATOR_KEYS = {
    "PRESERVE": {"op", "fields"},
    "VERIFY": {"op", "fields"},
    "TRANSITION": {"op", "from", "to"},
    "ACTIVATE": {"op", "regime", "modules"},
    "FALLBACK": {"op", "regime"},
}
MISSING = object()


class InvalidGrammar(ValueError):
    """Reject malformed or out-of-bounds untrusted grammar declarations."""


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _object(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise InvalidGrammar(name + " must be an object")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        raise InvalidGrammar(name + " must be a nonempty bounded string")
    return value


def _unique_strings(value: Any, name: str, limit: int = MAX_FIELDS) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise InvalidGrammar(name + " must be a bounded array")
    result = [_string(v, name + " item") for v in value]
    if len(set(result)) != len(result):
        raise InvalidGrammar(name + " contains duplicates")
    return result


def _cost(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidGrammar(name + " must be numeric")
    result = float(value)
    if not 0 <= result <= 1e12 or result != result:
        raise InvalidGrammar(name + " must be finite, nonnegative, and bounded")
    return result


def validate_contract(contract: dict) -> dict:
    c = _object(contract, "contract")
    if c.get("schema") != CONTRACT_SCHEMA:
        raise InvalidGrammar("unsupported contract schema")
    required = _unique_strings(c.get("required_fields"), "required_fields")
    exact = _unique_strings(c.get("exact_fields", []), "exact_fields")
    if not set(exact).issubset(required):
        raise InvalidGrammar("exact_fields must be required")
    for key in ("task", "source_id"):
        _string(c.get(key), key)
    return {"schema": CONTRACT_SCHEMA, "task": c["task"], "source_id": c["source_id"],
            "required_fields": required, "exact_fields": exact}


def validate_grammar(grammar: dict) -> dict:
    g = _object(grammar, "grammar")
    if g.get("schema") != SCHEMA:
        raise InvalidGrammar("unsupported grammar schema")
    regimes = _object(g.get("regimes"), "regimes")
    if not 1 <= len(regimes) <= MAX_REGIMES:
        raise InvalidGrammar("regimes must be nonempty and bounded")
    operators = g.get("operators")
    if not isinstance(operators, list) or len(operators) > MAX_OPERATORS:
        raise InvalidGrammar("operators must be a bounded list")
    for i, op in enumerate(operators):
        o = _object(op, "operator")
        if o.get("op") not in OPERATORS:
            raise InvalidGrammar("unsupported operator at " + str(i))
        if not set(o) <= OPERATOR_KEYS[o["op"]]:
            raise InvalidGrammar("unsupported key in " + o["op"] + " operator at " + str(i))
        if o["op"] == "TRANSITION":
            if o.get("from") not in regimes or o.get("to") not in regimes:
                raise InvalidGrammar("transition endpoints must exist")
        elif o["op"] == "ACTIVATE":
            if o.get("regime") not in regimes:
                raise InvalidGrammar("activation regime must exist")
            _unique_strings(o.get("modules", []), "modules")
        elif o["op"] in ("PRESERVE", "VERIFY"):
            _unique_strings(o.get("fields", []), "operator fields")
        elif o["op"] == "FALLBACK":
            if o.get("regime") not in regimes:
                raise InvalidGrammar("fallback regime must exist")
    for name, value in regimes.items():
        _string(name, "regime id")
        r = _object(value, "regime")
        fields = _unique_strings(r.get("preserves"), "regime preserves")
        unknown = _unique_strings(r.get("unknown_fields", []), "regime unknown_fields")
        if set(fields).intersection(unknown):
            raise InvalidGrammar("field cannot be preserved and unknown")
        _cost(r.get("payload_bytes"), "payload_bytes")
        _cost(r.get("activation_ms"), "activation_ms")
        _cost(r.get("model_bytes", 0), "model_bytes")
        if "exact_fields" in r:
            exactly = _unique_strings(r["exact_fields"], "regime exact_fields")
            if not set(exactly).issubset(fields):
                raise InvalidGrammar("regime exact_fields must be preserved")
    return g


def evaluate(grammar: dict, contract: dict, observations: dict, *, max_activation_ms: float,
             max_model_bytes: float, baseline_regime: str | None = None) -> dict:
    """Return finite declared-constraint assessment, never domain-level ADMIT.

    Per-field observations must be actual caller-provided scalar values; they
    are not inferred from prose. Missing evidence returns UNKNOWN. Claimed
    preservation is not independent verification and remains INCONCLUSIVE.
    """
    g = validate_grammar(grammar)
    c = validate_contract(contract)
    obs = _object(observations, "observations")
    if len(obs) > MAX_FIELDS:
        raise InvalidGrammar("too many observations")
    for key, value in obs.items():
        _string(key, "observation field")
        if not isinstance(value, (str, int, float, bool)) or (
            isinstance(value, str) and len(value) > MAX_TEXT
        ):
            raise InvalidGrammar("observations must be bounded scalar values")
    budget_ms = _cost(max_activation_ms, "max_activation_ms")
    budget_bytes = _cost(max_model_bytes, "max_model_bytes")
    if baseline_regime is not None and baseline_regime not in g["regimes"]:
        raise InvalidGrammar("baseline regime missing")
    required = set(c["required_fields"])
    exact = set(c["exact_fields"])
    # PRESERVE/VERIFY are declarations, but they must name fields the contract governs;
    # a field the contract does not know about cannot be preserved or verified against it.
    for i, op in enumerate(g["operators"]):
        if op["op"] in ("PRESERVE", "VERIFY"):
            stray = sorted(set(op.get("fields", [])) - required)
            if stray:
                raise InvalidGrammar(op["op"] + " at " + str(i) + " names fields outside the contract: " + ", ".join(stray))
    receipts = []
    for regime_id, cfg in sorted(g["regimes"].items()):
        preserved = set(cfg["preserves"])
        uncertain = set(cfg.get("unknown_fields", []))
        exact_preserved = set(cfg.get("exact_fields", []))
        absent = sorted(required - preserved - uncertain)
        unresolved = sorted((required & uncertain) | (required - set(obs)))
        weakened = sorted(exact - exact_preserved)
        constraints = []
        if absent:
            constraints.append("MISSING_REQUIRED_FIELDS")
        if weakened:
            constraints.append("EXACT_FIDELITY_NOT_DECLARED")
        if cfg["activation_ms"] > budget_ms:
            constraints.append("ACTIVATION_BUDGET_EXCEEDED")
        if cfg.get("model_bytes", 0) > budget_bytes:
            constraints.append("MODEL_BUDGET_EXCEEDED")
        if constraints:
            verdict = "UNSAT"
        elif unresolved:
            verdict = "UNKNOWN"
        else:
            verdict = "SAT"
        receipts.append({
            "regime": regime_id, "finite_constraint_result": verdict,
            "admission": "INCONCLUSIVE", "can_generate": False,
            "violations": constraints, "unresolved": unresolved,
            "lost_fields": absent, "weakened_exact_fields": weakened,
            "payload_bytes": cfg["payload_bytes"],
            "activation_ms": cfg["activation_ms"],
            "model_bytes": cfg.get("model_bytes", 0),
            "estimated_cost": cfg["payload_bytes"] + cfg.get("model_bytes", 0),
        })
    feasible = [r for r in receipts if r["finite_constraint_result"] == "SAT"]
    candidate = min(feasible, key=lambda r: (r["estimated_cost"], r["activation_ms"], r["regime"])) if feasible else None
    baseline = next((r for r in receipts if r["regime"] == baseline_regime), None)
    return {
        "schema": "qualityrag.activation-assessment/v0.1",
        "grammar_sha256": digest(g), "contract_sha256": digest(c),
        "observations_sha256": digest(obs), "source_id": c["source_id"],
        "finite_constraint_result": "SAT" if candidate else ("UNKNOWN" if any(
            r["finite_constraint_result"] == "UNKNOWN" for r in receipts) else "UNSAT"),
        "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
        "selected_candidate": candidate["regime"] if candidate else None,
        "baseline": baseline, "regimes": receipts,
        "disclaimer": "Finite declared constraints only; no authenticated evidence, semantic fidelity, video decoding or production admission.",
    }
