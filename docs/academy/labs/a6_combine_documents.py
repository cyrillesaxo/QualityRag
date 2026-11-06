"""A6 · It can't combine several documents. (available pattern + research preview)"""
import json
from _common import AS_OF, ev, evaluate, show
import _research  # noqa: F401
from explicit_relation_extraction import extract_declared_relations

# Available now: one answer, three documents. Each requirement is met by a different file.
pack = {"id": "vendor-onboarding", "version": "1.0", "requirements": [
    {"id": "contract-signed", "min_independent_sources": 1},
    {"id": "security-review", "min_independent_sources": 1},
    {"id": "dpa-in-place", "min_independent_sources": 1}]}
two_files = [ev("msa-2026.pdf#p12", "contract-signed", "legal-repository"),
             ev("SEC-4471", "security-review", "security-tickets")]
show("Two of the three files retrieved", evaluate(pack, two_files, as_of=AS_OF))
show("All three files", evaluate(pack, two_files + [ev("dpa-v3.docx#s4", "dpa-in-place", "privacy-office")], as_of=AS_OF))

# Research preview: links between documents are explicit, source-anchored candidates, never facts.
sources = [
    {"id": "msa", "text": "Master services agreement, signed 2026-02-01.\nRELATE msa REQUIRES dpa\n"},
    {"id": "dpa", "text": "Data processing agreement v3.\nThe DPA covers the security review.\nRELATE dpa REFERENCES sec\n"},
    {"id": "sec", "text": "Security review SEC-4471 passed.\nRELATE sec covers msa\n"}]
out = extract_declared_relations(sources, principal="learner", authorize_source=lambda p, s, r: True)
print("\n== Declared links between documents (research)")
for c in out["candidates"]:
    print(f"  {c['from']} -{c['relation']}-> {c['to']}   at {c['evidence_source']} line {c['anchor']['line']}")
for bad in out["invalid_declarations"]:
    print(f"  {bad['source_id']} line {bad['line']}: {bad['status']}")
print(f"  interpretation: {out['interpretation']}")
print(f"  admission: {out['admission']}   can_generate: {out['can_generate']}")
