import copy
import unittest

from qualityrag.discovery import discover

PACK = {
    "id": "eligibility", "version": "1",
    "requirements": [{"id": "eligibility_rule", "min_independent_sources": 2,
                      "scope": "GA", "authority": "official"}],
}
NOW = "2026-11-05T10:00:00Z"
GRAPH = {
    "nodes": [
        {"id": "policy", "source_ref": "doc:policy", "scope": "GA"},
        {"id": "exception", "source_ref": "doc:exception", "scope": "GA",
         "authority": "official", "proposed_requirement_id": "special_case"},
        {"id": "alternate", "source_ref": "doc:alternate", "scope": "FL",
         "authority": "unverified"},
    ],
    "edges": [
        {"source": "policy", "target": "exception", "relation": "EXCEPTS",
         "source_ref": "doc:policy"},
        {"source": "policy", "target": "alternate", "relation": "FUNCTIONAL_SIBLING",
         "source_ref": "doc:policy"},
        {"source": "exception", "target": "policy", "relation": "PART_OF",
         "source_ref": "doc:exception"},
    ],
}
SEEDS = [{"requirement_id": "eligibility_rule", "entity_id": "policy"}]


class DiscoveryTests(unittest.TestCase):
    def run_discovery(self, evidence=None, **kwargs):
        return discover(PACK, [] if evidence is None else evidence, GRAPH, SEEDS,
                        as_of=NOW, **kwargs)

    def test_missing_evidence_produces_only_proposals(self):
        before = copy.deepcopy(PACK)
        result = self.run_discovery()
        self.assertEqual(result["baseline_verdict"], "INCONCLUSIVE")
        self.assertEqual(result["discovery_verdict"], "INCONCLUSIVE")
        self.assertFalse(result["can_generate"])
        self.assertFalse(result["policy_changed"])
        self.assertEqual(PACK, before)
        self.assertEqual({x["entity_id"] for x in result["candidates"]},
                         {"exception", "alternate", "policy"})
        self.assertEqual(result["proposed_obligations"][0]["proposed_requirement_id"],
                         "special_case")
        self.assertEqual(result["proposed_obligations"][0]["status"], "REVIEW_REQUIRED")

    def test_cross_scope_sibling_not_equated(self):
        result = self.run_discovery()
        by_id = {x["entity_id"]: x for x in result["candidates"]}
        self.assertTrue(by_id["alternate"]["context_mismatch"])
        self.assertEqual(by_id["alternate"]["status"], "UNVERIFIED_RETRIEVAL_TARGET")
        self.assertFalse(by_id["exception"]["context_mismatch"])

    def test_contradiction_is_not_erased(self):
        evidence = [{"id": "x", "origin": "official", "source_ref": "doc:x",
                     "requirement_id": "eligibility_rule", "status": "CONTRADICTS",
                     "observed_at": NOW, "scope": "GA", "authority": "official"}]
        result = self.run_discovery(evidence)
        self.assertEqual(result["baseline_verdict"], "REFUSE")
        self.assertFalse(result["can_generate"])

    def test_satisfied_obligation_has_no_evidence_candidates(self):
        evidence = [
            {"id": str(i), "origin": "source-" + str(i),
             "source_ref": "doc:" + str(i), "requirement_id": "eligibility_rule",
             "status": "SUPPORTS", "observed_at": NOW, "scope": "GA",
             "authority": "official"} for i in (1, 2)
        ]
        result = self.run_discovery(evidence)
        self.assertEqual(result["baseline_verdict"], "ADMIT")
        self.assertEqual(result["candidates"], [])
        # Unknown obligations remain advisory even when declared obligations pass.
        self.assertEqual(len(result["proposed_obligations"]), 1)
        self.assertFalse(result["can_generate"])

    def test_cycle_and_zero_budget(self):
        result = self.run_discovery(max_depth=0)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["search"]["visited_states"], 1)
        self.assertLessEqual(self.run_discovery()["search"]["visited_states"], 3)

    def test_invalid_edges_fail_closed(self):
        graph = copy.deepcopy(GRAPH)
        graph["edges"][0].pop("source_ref")
        with self.assertRaises(ValueError):
            discover(PACK, [], graph, SEEDS, as_of=NOW)
        with self.assertRaises(ValueError):
            self.run_discovery(max_depth=-1)
        with self.assertRaises(ValueError):
            discover(PACK, [], GRAPH, [{"requirement_id": "unknown",
                                       "entity_id": "policy"}], as_of=NOW)

    def test_hard_candidate_limit(self):
        result = self.run_discovery(max_candidates=1)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertTrue(result["search"]["truncated"])


if __name__ == "__main__":
    unittest.main()
