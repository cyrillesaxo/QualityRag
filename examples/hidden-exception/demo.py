import json
from qualityrag.compiler import evaluate_compiled
pack={"id":"synthetic.enrollment","version":"1","requirements":[
 {"id":"general-rule","min_independent_sources":1,"scope":"GA","authority":"official"},
 {"id":"current-exception","min_independent_sources":1,"scope":"GA","authority":"official"}]}
evidence=[{"id":"rule-1","requirement_id":"general-rule","origin":"policy-rule","source_ref":"synthetic:rule",
 "status":"SUPPORTS","scope":"GA","authority":"official","observed_at":"2026-11-02T10:00:00Z"}]
result=evaluate_compiled(pack,evidence,as_of="2026-11-02T10:05:00Z")
assert result["verdict"]=="INCONCLUSIVE"
assert any(x["requirement_id"]=="current-exception" for x in result["wgap"])
print(json.dumps({"naive_unsupported_answer":"Eligible","qualityrag":result},indent=2))
