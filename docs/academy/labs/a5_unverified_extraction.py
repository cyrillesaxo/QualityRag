"""A5 · Your PDF parser silently changed the numbers. How would you know? (research preview)"""
from _common import AS_OF, ev, evaluate, show

pack = {"id": "fee-schedule", "version": "1.0",
        "requirements": [{"id": "wire-fee-eur", "min_independent_sources": 1}]}
# A value read from a parsed PDF table that nobody has checked against the page is UNKNOWN, not SUPPORTS.
parsed_cell = ev("fees.pdf#page=4:row=7:col=3", "wire-fee-eur", "fee-schedule-2026", status="UNKNOWN")
show("Parsed table cell, unverified", evaluate(pack, [parsed_cell], as_of=AS_OF))
checked = dict(parsed_cell, status="SUPPORTS", id="fees.pdf#page=4:row=7:col=3:reviewed")
show("Same cell after a reviewer checked the page", evaluate(pack, [checked], as_of=AS_OF))
