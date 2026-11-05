"""A4 · It uses outdated policies, and picks one side of a contradiction."""
from _common import AS_OF, ev, evaluate, show

pack = {"id": "restart-policy", "version": "1.0",
        "requirements": [{"id": "restart-procedure", "min_independent_sources": 1, "max_age_seconds": 365 * 24 * 3600}]}
runbook_2024 = ev("runbook-restart", "restart-procedure", "legacy-runbook", observed="2024-03-01T00:00:00Z")
show("Only the 2024 runbook", evaluate(pack, [runbook_2024], as_of=AS_OF))
current = ev("ops-7.3", "restart-procedure", "ops-handbook")
memo = ev("memo-supersedes", "restart-procedure", "regional-change-memo", status="CONTRADICTS")
show("Current handbook vs a contradicting memo", evaluate(pack, [runbook_2024, current, memo], as_of=AS_OF))
