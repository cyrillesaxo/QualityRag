"""Recorded, labelled cases for the measurement labs (synthetic; the labels say what a reviewer decided)."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
sys.path.insert(0, ROOT)
from _common import AS_OF, ev  # noqa: E402

PACK = {"id": "gateway-recovery", "version": "1.0", "requirements": [
    {"id": "recovery-procedure", "min_independent_sources": 1, "max_age_seconds": 365 * 24 * 3600}]}
STRICT = {"id": "gateway-recovery", "version": "1.1-two-origins", "requirements": [
    {"id": "recovery-procedure", "min_independent_sources": 2, "max_age_seconds": 365 * 24 * 3600}]}

R = "recovery-procedure"
DEMO = [  # the clean cases a demo is built from: current handbook plus an independent change record
    {"id": "demo-1", "expect_admit": True, "evidence": [ev("ops-7.3", R, "ops-handbook"), ev("cab-0412", R, "change-board")]},
    {"id": "demo-2", "expect_admit": True, "evidence": [ev("ops-7.3", R, "ops-handbook"), ev("sre-ticket-88", R, "sre-tickets")]},
    {"id": "demo-3", "expect_admit": True, "evidence": [ev("ops-7.4", R, "ops-handbook"), ev("cab-0415", R, "change-board")]},
    {"id": "demo-4", "expect_admit": False, "evidence": []},
]
FIELD = [  # what production retrieval actually returns
    {"id": "field-copies", "expect_admit": False, "evidence": [ev("ops-7.3", R, "ops-handbook"), ev("ops-mirror-7.3", R, "ops-handbook")]},
    {"id": "field-forwarded", "expect_admit": False, "evidence": [ev("fwd-email-7.3", R, "ops-handbook")]},
    {"id": "field-stale", "expect_admit": False, "evidence": [ev("runbook-2024", R, "legacy-runbook", observed="2024-03-01T00:00:00Z")]},
    {"id": "field-good", "expect_admit": True, "evidence": [ev("ops-7.3", R, "ops-handbook"), ev("cab-0412", R, "change-board")]},
    {"id": "field-wiki-only", "expect_admit": False, "evidence": [ev("wiki-recovery", R, "team-wiki")]},
    {"id": "field-good-2", "expect_admit": True, "evidence": [ev("ops-7.4", R, "ops-handbook"), ev("sre-ticket-91", R, "sre-tickets")]},
    {"id": "field-regulator", "expect_admit": True, "evidence": [ev("reg-notice-12", R, "regulator")]},  # one authoritative source
]
