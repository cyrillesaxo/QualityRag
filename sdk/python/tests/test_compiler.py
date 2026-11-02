import unittest
from qualityrag.compiler import compile_pack, evaluate_compiled

PACK = {"id":"policy","version":"1","requirements":[
    {"id":"eligibility","min_independent_sources":2,"max_age_seconds":3600,"scope":"GA","authority":"official"}]}
NOW = "2026-11-02T10:05:00Z"
def witness(id, origin, *, status="SUPPORTS", scope="GA", authority="official"):
    return {"id":id,"origin":origin,"requirement_id":"eligibility","source_ref":"doc:"+id,
            "status":status,"scope":scope,"authority":authority,"observed_at":"2026-11-02T10:00:00Z"}

class CompilerTests(unittest.TestCase):
    def test_compile(self):
        ir=compile_pack(PACK)
        self.assertEqual(ir[0].required_scope,"GA")
    def test_shared_origin_gap(self):
        result=evaluate_compiled(PACK,[witness("a","one"),witness("b","one")],as_of=NOW)
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertEqual(result["wgap"][0]["missing_sources"],1)
        self.assertEqual(len(result["witness_graph"]["dependent_groups"]),1)
    def test_scope_and_authority_mismatch(self):
        result=evaluate_compiled(PACK,[witness("a","one",scope="FL"),witness("b","two",authority="unverified")],as_of=NOW)
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertIn("SCOPE_MISMATCH",result["findings"][0]["reasons"])
        self.assertIn("AUTHORITY_MISMATCH",result["findings"][0]["reasons"])
    def test_contradiction(self):
        result=evaluate_compiled(PACK,[witness("a","one"),witness("b","two"),witness("c","three",status="CONTRADICTS")],as_of=NOW)
        self.assertEqual(result["verdict"],"REFUSE")
    def test_success(self):
        result=evaluate_compiled(PACK,[witness("a","one"),witness("b","two")],as_of=NOW)
        self.assertEqual(result["verdict"],"ADMIT")
        self.assertEqual(result["wgap"],[])
    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            compile_pack({**PACK,"requirements":[{"id":"r"},{"id":"r"}]})
