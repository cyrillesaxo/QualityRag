"""Transparent lifecycle scenarios and Pareto candidates, not observed savings."""
import math

COMPONENTS = ("compile", "encode", "residual", "model_distribution", "update",
              "storage", "bandwidth", "decode", "verification", "energy", "review")


def lifecycle(values):
    if not isinstance(values, dict) or set(values) != set(COMPONENTS):
        raise ValueError("Every lifecycle cost component must be declared")
    unknown, total, assumptions = [], 0.0, []
    for name in COMPONENTS:
        item = values[name]
        if not isinstance(item, dict) or set(item) != {"value", "evidence", "unit"} or item["unit"] != "USD":
            raise ValueError("Cost value, evidence classification and common currency required")
        value = item["value"]
        if item["evidence"] not in {"OBSERVED", "ASSUMED", "UNKNOWN"}:
            raise ValueError("Unknown cost evidence class")
        if item["evidence"] == "UNKNOWN":
            if value is not None:
                raise ValueError("Unknown costs must have null value")
            unknown.append(name)
        else:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Finite nonnegative cost required")
            total += value
            if item["evidence"] == "ASSUMED":
                assumptions.append(name)
    return {"total_usd": None if unknown else total, "known_subtotal_usd": total,
            "unknown_components": unknown, "assumed_components": assumptions,
            "classification": "INCONCLUSIVE" if unknown else ("SCENARIO" if assumptions else "OBSERVED_INPUT_SUM"),
            "economic_advantage": "NOT_ESTABLISHED"}


def pareto(candidates):
    """Minimize bytes, latency and energy only after all declared fidelity checks pass."""
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 128:
        raise ValueError("Bounded candidate set required")
    seen = set()
    eligible = []
    for row in candidates:
        if not isinstance(row, dict) or set(row) != {"id", "bytes", "latency_ms", "energy_j", "fidelity_pass"}:
            raise ValueError("Explicit Pareto dimensions required")
        from .common import identity
        identity(row["id"])
        if row["id"] in seen or type(row["fidelity_pass"]) is not bool:
            raise ValueError("Duplicate candidate or invalid fidelity")
        seen.add(row["id"])
        for k in ("bytes", "latency_ms", "energy_j"):
            if type(row[k]) not in (int, float) or not math.isfinite(row[k]) or row[k] < 0:
                raise ValueError("Invalid measured dimension")
        if row["fidelity_pass"]:
            eligible.append(row)
    dimensions = ("bytes", "latency_ms", "energy_j")
    return sorted(a["id"] for a in eligible if not any(
        all(b[k] <= a[k] for k in dimensions) and any(b[k] < a[k] for k in dimensions)
        for b in eligible if b["id"] != a["id"]))
