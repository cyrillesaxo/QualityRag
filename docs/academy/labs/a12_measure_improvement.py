"""A12 · We can't measure whether our RAG is improving. (experimental)"""
from _cases import PACK, STRICT, DEMO, FIELD, AS_OF
from tools.activation_runtime.governance import replay

r = replay(PACK, STRICT, DEMO + FIELD, as_of=AS_OF)
print(f"== {r['cases']} recorded cases · {r['labeled']['expect_admit']} should answer · {r['labeled']['expect_refusal']} should not")
for side in ("base", "branch"):
    s = r[side]
    print(f"  {s['pack']:<34} answer rate {s['answer_rate']:.0%}   false admissions {s['false_admission_rate']:.0%}")
print(f"  {r['note']}")
