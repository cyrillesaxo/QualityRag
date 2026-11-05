"""Functional-sibling feasibility and regime boundaries over the QualityRag gate.

Implements the relations proposed in "Functional-Sibling Discovery and Regime Convergence"
(working paper v4, 5 Nov 2026), sections 2.1, 2.2, 5 and 5.2:

    Feasible(s, F, C)              gate verdict of candidate s's evidence against contract C
    FunctionalSibling(a, b | F, C) Feasible(a, F, C) and Feasible(b, F, C), a != b
    D(F, C)                        the feasible subset of the candidates supplied
    regime transition              a candidate whose status changes between contracts

Status is SAT (ADMIT), UNSAT (REFUSE: contradicting evidence) or UNKNOWN (INCONCLUSIVE),
never a forced binary. Siblinghood is relative to one contract and is not equivalence:
performance, durability or cost are compared only if the contract requires them. D(F, C) is
the discovered subset of an open world, not the complete set.
"""
from __future__ import annotations

import copy
import itertools

from .governance import compile_pack, evaluate_compiled, _string  # shares the gate import path

STATUS = {"ADMIT": "SAT", "REFUSE": "UNSAT", "INCONCLUSIVE": "UNKNOWN"}
LIMITS = {"candidates": 500, "contracts": 20, "evidence": 200}


def feasibility(function: str, contracts: dict, candidates: list, *, as_of: str) -> dict:
    """Evaluate every candidate against every contract and derive siblings and boundaries."""
    _string(function, "function", 200)
    if not isinstance(contracts, dict) or not 0 < len(contracts) <= LIMITS["contracts"]:
        raise ValueError("contracts must be a nonempty object of name -> PackSpec")
    for name, pack in contracts.items():
        _string(name, "contract name", 100)
        compile_pack(pack)
    if not isinstance(candidates, list) or not 0 < len(candidates) <= LIMITS["candidates"]:
        raise ValueError("candidates must be a nonempty list")
    ids = []
    for c in candidates:
        if not isinstance(c, dict) or not set(c) <= {"id", "label", "mechanism_family", "evidence", "branch"}:
            raise ValueError("candidate needs id and evidence; optional label, mechanism_family, branch")
        ids.append(_string(c.get("id"), "candidate id", 100))
        if not isinstance(c.get("evidence"), list) or len(c["evidence"]) > LIMITS["evidence"]:
            raise ValueError("candidate evidence must be a list")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate candidate id")

    names = list(contracts)
    matrix = []
    for c in candidates:
        row = {"candidate": c["id"], "label": c.get("label"), "mechanism_family": c.get("mechanism_family"),
               "branch": c.get("branch"), "contracts": {}}
        for name in names:
            result = evaluate_compiled(contracts[name], copy.deepcopy(c["evidence"]), as_of=as_of)
            row["contracts"][name] = {
                "status": STATUS[result["verdict"]], "verdict": result["verdict"],
                "requirements": [{"requirement_id": f["requirement_id"], "status": STATUS[f["verdict"]],
                                  "independent_sources": f["independent_sources"], "reasons": f["reasons"]}
                                 for f in result["findings"]]}
        matrix.append(row)

    per_contract = {}
    for name in names:
        by = {s: [r["candidate"] for r in matrix if r["contracts"][name]["status"] == s] for s in ("SAT", "UNSAT", "UNKNOWN")}
        pack = contracts[name]
        per_contract[name] = {
            "pack": f"{pack['id']}@{pack['version']}",
            "feasible": by["SAT"], "rejected": by["UNSAT"], "unknown": by["UNKNOWN"],
            "sibling_pairs": len(by["SAT"]) * (len(by["SAT"]) - 1) // 2,
            "siblings": by["SAT"] if len(by["SAT"]) > 1 else [],
            "relation": f"FunctionalSibling(·,· | {function}, {name})",
        }

    boundaries = []
    for a, b in itertools.combinations(names, 2):
        for r in matrix:
            x, y = r["contracts"][a]["status"], r["contracts"][b]["status"]
            if x != y:
                changed = sorted({q["requirement_id"] for q in r["contracts"][b]["requirements"] if q["status"] != "SAT"} |
                                 {q["requirement_id"] for q in r["contracts"][a]["requirements"] if q["status"] != "SAT"})
                boundaries.append({"candidate": r["candidate"], "from_contract": a, "to_contract": b,
                                   "from": x, "to": y, "deciding_requirements": changed})

    # Discriminating experiments: each UNKNOWN requirement is evidence to collect next (paper §6.1).
    probes = [{"candidate": r["candidate"], "contract": name, "requirement_id": q["requirement_id"],
               "missing_sources": max(0, next(o.min_origins for o in compile_pack(contracts[name])
                                              if o.requirement_id == q["requirement_id"]) - q["independent_sources"]),
               "reasons": q["reasons"]}
              for r in matrix for name in names for q in r["contracts"][name]["requirements"] if q["status"] == "UNKNOWN"]

    families = {}
    for r in matrix:
        if r["mechanism_family"]:
            families.setdefault(r["mechanism_family"], []).append(r["candidate"])

    return {
        "schema": "qualityrag.functional-siblings/v0.1", "function": function, "as_of": as_of,
        "contracts": per_contract, "matrix": matrix, "regime_boundaries": boundaries, "probes": probes,
        "mechanism_families": families,
        "coverage": {
            "candidates_evaluated": len(matrix),
            "statement": "D(F, C) is the feasible subset of the candidates supplied. In an open world it is a "
                         "discovered set, not the complete set; unknown candidates and unsearched regions remain.",
        },
        "guards": [
            "Siblinghood holds only under the named contract; it is not semantic or functional equivalence.",
            "SAT is evidence-metadata satisfaction of every requirement in the contract, not engineering approval.",
            "UNKNOWN means missing or unknown evidence, not failure. UNSAT requires contradicting evidence.",
            "A boundary shows where the status changes for these candidates; it is not evidence of a hidden cause.",
        ],
    }


def example() -> dict:
    """Section 4 of the working paper (joining two components), restated as data.

    The paper calls this an illustrative thought experiment, not a measured dataset. Every
    evidence row cites the paper's own statement; none is an engineering measurement.
    """
    at = "2026-11-05T00:00:00Z"
    ref = "functional-sibling-paper-v4#s4"

    def row(cid, req, status, note):
        return {"id": f"{cid}:{req}", "requirement_id": req, "status": status, "origin": "functional-sibling-paper-v4",
                "source_ref": ref, "observed_at": at, "note": note}

    joins = "joins-two-components"
    separation = "repeatable-nondestructive-separation"
    shared = "Paper §4: shares the high-level outcome JOIN_COMPONENTS."
    cands = [
        ("screw", "mechanical fastening", []),
        ("bolt", "mechanical fastening", []),
        ("clamp", "mechanical fastening", []),
        ("hook-and-loop", "mechanical fastening", []),
        ("rivet", "mechanical fastening", [row("rivet", separation, "CONTRADICTS", "Paper §4: permanent rivets fail repeatable nondestructive separation.")]),
        ("adhesive", "chemical bonding", [row("adhesive", separation, "UNKNOWN", "Paper §4: many adhesive joints fail; not all.")]),
        ("weld", "thermal joining", [row("weld", separation, "UNKNOWN", "Paper §4: many welds fail; not all.")]),
    ]
    candidates = [{"id": cid, "mechanism_family": family, "evidence": [row(cid, joins, "SUPPORTS", shared), *extra]}
                  for cid, family, extra in cands]
    return {
        "function": "JOIN_COMPONENTS",
        "contracts": {
            "join": {"id": "join-components", "version": "1.0",
                     "requirements": [{"id": joins, "min_independent_sources": 1}]},
            "join-and-separate": {"id": "join-components-separable", "version": "1.0",
                                  "requirements": [{"id": joins, "min_independent_sources": 1},
                                                   {"id": separation, "min_independent_sources": 1}]},
        },
        "candidates": candidates, "as_of": "2026-11-05T12:00:00Z",
        "source": "Functional-Sibling Discovery and Regime Convergence, working paper v4, section 4",
        "illustrative": True,
        "note": "Thought experiment from the paper, not measured data. Evidence rows restate the paper's statements "
                "and all share one origin, so nothing here is independently supported.",
    }
