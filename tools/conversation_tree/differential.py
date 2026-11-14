"""Differential branch test comparator (US-074).

Compares what two branches declared they decided, not their wording. It is independent of
the drift classifier. The caller runs both branches under the same model and budget; a
mismatch is refused as not comparable. Anything the comparator cannot decide is UNKNOWN,
which is handled as DIVERGE.
"""
from __future__ import annotations

COMPARATOR = "qualityrag.conversation-differential/v0.1"
_SCALAR = (str, int, float, bool)


def _decisions(answer):
    value = answer.get("decisions")
    if (not isinstance(value, dict) or not value
            or not all(isinstance(k, str) and isinstance(v, _SCALAR) for k, v in value.items())):
        return None
    return value


def _cost(answer):
    value = answer.get("cost")
    if isinstance(value, dict) and value and all(type(v) in (int, float) and v >= 0 for v in value.values()):
        return {"label": "OBSERVED", **value}
    return {"label": "UNKNOWN"}


def compare(isolated, merged):
    for answer in (isolated, merged):
        if not isinstance(answer, dict) or not isinstance(answer.get("model_version"), str):
            raise ValueError("Each answer needs a branch, model_version, budget and decisions")
    if isolated["model_version"] != merged["model_version"] or isolated.get("budget") != merged.get("budget"):
        raise ValueError("Not comparable: model version and budget must match")
    left, right = _decisions(isolated), _decisions(merged)
    if left is None or right is None:
        verdict, differences = "UNKNOWN", []
    else:
        differences = [{"decision": key, "isolated": left.get(key), "merged": right.get(key)}
                       for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key)]
        verdict = "DIVERGE" if differences else "AGREE"
    return {"verdict": verdict, "handled_as": "AGREE" if verdict == "AGREE" else "DIVERGE",
            "differences": differences, "comparator": COMPARATOR,
            "model_version": isolated["model_version"], "budget": isolated.get("budget"),
            "cost": {"isolated": _cost(isolated), "merged": _cost(merged)}}
