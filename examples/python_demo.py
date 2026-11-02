import json
from qualityrag import evaluate

pack={"id":"example.answer","version":"1","requirements":[{"id":"eligibility","min_independent_sources":2,"max_age_seconds":86400}]}
evidence=[{"id":"w1","requirement_id":"eligibility","origin":"document-A","source_ref":"doc:A#1","status":"SUPPORTS","observed_at":"2026-11-02T10:00:00Z"}]
result=evaluate(pack,evidence,as_of="2026-11-02T11:00:00Z")
print(json.dumps(result,indent=2))
assert result["verdict"]=="INCONCLUSIVE"
