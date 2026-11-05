"""A1 · It found the right document, but gave the wrong answer."""
from _common import PACK, AS_OF, ev, evaluate, show

# What a typical retriever returns: relevant, recent, and incomplete.
top4 = [ev("ops-7.3", "recovery-procedure", "ops-handbook")]  # incident + 2024 runbook link to no requirement
show("Retrieved top-4 passages", evaluate(PACK, top4, as_of=AS_OF))

# Targeted retrieval adds the annex (with its "unless") and the regional memo.
full = top4 + [ev("annex-d-187", "eu-screening-control", "eu-control-annex"),
               ev("memo-exception", "approval-or-exception", "regional-change-memo")]
show("After targeted retrieval", evaluate(PACK, full, as_of=AS_OF))
