"""Shared fixture for QualityRag Academy labs: the synthetic EU payments corpus (all passages invented)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk", "python"))
from qualityrag import evaluate  # noqa: E402

AS_OF = "2026-11-05T12:00:00Z"
PACK = {"id": "eu-payments-screening-recovery", "version": "1.0", "requirements": [
    {"id": "recovery-procedure", "min_independent_sources": 1},
    {"id": "eu-screening-control", "min_independent_sources": 1},
    {"id": "approval-or-exception", "min_independent_sources": 1}]}


def ev(id, req, origin, status="SUPPORTS", observed="2026-09-01T00:00:00Z"):
    return {"id": id, "requirement_id": req, "origin": origin, "source_ref": id, "observed_at": observed, "status": status}


def show(title, result):
    print(f"\n== {title}")
    print(f"verdict: {result['verdict']}")
    for f in result["findings"]:
        reasons = ", ".join(f["reasons"]) or "-"
        print(f"  {f['requirement_id']:<22} {f['verdict']:<13} sources={f['independent_sources']}  {reasons}")
