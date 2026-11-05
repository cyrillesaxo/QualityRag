"""A2 · It confidently invents an answer when the evidence is missing."""
from _common import PACK, AS_OF, ev, evaluate, show


def answer_or_withhold(question, evidence):
    result = evaluate(PACK, evidence, as_of=AS_OF)
    if result["verdict"] != "ADMIT":
        gap = [f["requirement_id"] for f in result["findings"] if f["verdict"] != "ADMIT"]
        return f"WITHHELD ({result['verdict']}): missing evidence for {', '.join(gap)}"
    return "GENERATE: call the model with the admitted evidence"


q = "Can on-call restore the EU gateway after a screening failure?"
print(answer_or_withhold(q, [ev("ops-7.3", "recovery-procedure", "ops-handbook")]))
print(answer_or_withhold(q, [ev("ops-7.3", "recovery-procedure", "ops-handbook"),
                             ev("annex-d-187", "eu-screening-control", "eu-control-annex"),
                             ev("memo-exception", "approval-or-exception", "regional-change-memo")]))
