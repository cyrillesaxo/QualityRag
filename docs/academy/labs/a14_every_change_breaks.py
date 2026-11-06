"""A14 · Every change breaks something. (experimental)"""
from _cases import PACK, STRICT, DEMO, FIELD, AS_OF
from tools.activation_runtime.governance import replay

r = replay(PACK, STRICT, DEMO + FIELD, as_of=AS_OF)
d = r["pack_diff"]
print(f"== Replay {r['base']['pack']} -> {r['branch']['pack']} on {r['cases']} recorded cases")
for c in d:
    print(f"  change: {c['requirement_id']} {c['field']} {c['from']} -> {c['to']}")
print(f"  {r['flipped']} verdicts changed")
for f in r["flips"]:
    print(f"  {f['id']:<18} {f['from']:<12} -> {f['to']:<12} {f['effect']}")
e = r["effects"]
print(f"  false admissions removed {e['false_admission_removed']} · correct answers lost {e['correct_answer_lost']}")
