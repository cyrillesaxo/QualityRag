import unittest
from qualityrag import evaluate

PACK = {"id":"demo","version":"1","requirements":[{"id":"policy","min_independent_sources":2,"max_age_seconds":3600}]}
E = lambda id, origin, status="SUPPORTS": {"id":id,"origin":origin,"requirement_id":"policy","source_ref":"source:"+id,"status":status,"observed_at":"2026-11-02T10:00:00Z"}
NOW = "2026-11-02T10:05:00Z"

class EvaluationTests(unittest.TestCase):
    def test_independent_sources_admit(self):
        self.assertEqual(evaluate(PACK,[E("a","x"),E("b","y")],as_of=NOW)["verdict"],"ADMIT")
    def test_duplicate_origin_inconclusive(self):
        self.assertEqual(evaluate(PACK,[E("a","x"),E("b","x")],as_of=NOW)["verdict"],"INCONCLUSIVE")
    def test_contradiction_refuses(self):
        self.assertEqual(evaluate(PACK,[E("a","x"),E("b","y"),E("c","z","CONTRADICTS")],as_of=NOW)["verdict"],"REFUSE")
    def test_stale_is_not_admit(self):
        self.assertEqual(evaluate(PACK,[E("a","x"),{**E("b","y"),"observed_at":"2026-10-01T10:00:00Z"}],as_of=NOW)["verdict"],"INCONCLUSIVE")
    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            evaluate({"id":"x","version":"1","requirements":[{"id":"r"},{"id":"r"}]}, [], as_of=NOW)
