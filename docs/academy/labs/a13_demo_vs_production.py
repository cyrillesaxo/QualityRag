"""A13 · Excellent in the demo, unreliable in production. (experimental)"""
from _cases import PACK, DEMO, FIELD, AS_OF
from tools.activation_runtime.governance import replay


def score(name, cases):
    s = replay(PACK, PACK, cases, as_of=AS_OF)["base"]
    print(f"  {name:<28} {len(cases)} cases   answer rate {s['answer_rate']:.0%}   false admissions {s['false_admission_rate']:.0%}")


print(f"== One policy, {PACK['id']}@{PACK['version']}, two case sets")
score("demo cases", DEMO)
score("held-out production cases", FIELD)
