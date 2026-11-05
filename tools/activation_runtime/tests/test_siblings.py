"""Functional-sibling feasibility (paper §2.1/§5) and dependency-aware invalidation in the Gardener."""
import sys
import tempfile
import unittest
from pathlib import Path

from tools.activation_runtime import siblings as s
from tools.activation_runtime.gardener import LEDGER, Gardener, query

if LEDGER not in sys.path:
    sys.path.insert(0, LEDGER)
import ledger  # noqa: E402

AT = "2026-11-05T12:00:00Z"


def w(i, req, status, origin):
    return {"id": i, "requirement_id": req, "status": status, "origin": origin, "source_ref": origin + "#" + i, "observed_at": AT}


class FeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.ex = s.example()
        self.r = s.feasibility(self.ex["function"], self.ex["contracts"], self.ex["candidates"], as_of=self.ex["as_of"])

    def test_paper_example_is_open_world_not_binary(self):
        join, sep = self.r["contracts"]["join"], self.r["contracts"]["join-and-separate"]
        self.assertEqual(len(join["feasible"]), 7)
        self.assertEqual(join["sibling_pairs"], 21)
        self.assertEqual(sep["rejected"], ["rivet"])  # only the paper's explicit contradiction
        self.assertEqual(sep["feasible"], [])
        self.assertEqual(len(sep["unknown"]), 6)  # "many fail" and no evidence stay UNKNOWN
        self.assertTrue(self.ex["illustrative"])

    def test_regime_boundaries_and_probes(self):
        rivet = next(b for b in self.r["regime_boundaries"] if b["candidate"] == "rivet")
        self.assertEqual((rivet["from"], rivet["to"], rivet["deciding_requirements"]),
                         ("SAT", "UNSAT", ["repeatable-nondestructive-separation"]))
        self.assertEqual(len(self.r["regime_boundaries"]), 7)
        probed = {(p["candidate"], p["requirement_id"]) for p in self.r["probes"]}
        self.assertIn(("screw", "repeatable-nondestructive-separation"), probed)
        self.assertNotIn(("rivet", "repeatable-nondestructive-separation"), probed)

    def test_siblings_need_the_contract_and_independent_origins(self):
        contract = {"id": "c", "version": "1", "requirements": [{"id": "f", "min_independent_sources": 2}]}
        cands = [{"id": "a", "evidence": [w("a1", "f", "SUPPORTS", "lab-1"), w("a2", "f", "SUPPORTS", "lab-2")]},
                 {"id": "b", "evidence": [w("b1", "f", "SUPPORTS", "lab-1"), w("b2", "f", "SUPPORTS", "lab-1")]},  # copies
                 {"id": "c", "evidence": [w("c1", "f", "SUPPORTS", "lab-1"), w("c2", "f", "SUPPORTS", "lab-3")]}]
        r = s.feasibility("F", {"strict": contract}, cands, as_of=AT)
        self.assertEqual(r["contracts"]["strict"]["siblings"], ["a", "c"])
        self.assertEqual(r["contracts"]["strict"]["unknown"], ["b"])
        self.assertEqual(r["probes"][0]["missing_sources"], 1)
        self.assertEqual(r["regime_boundaries"], [])  # one contract: no transition to report

    def test_rejects_bad_input(self):
        good = self.ex["contracts"]
        for args in [("", good, self.ex["candidates"]), ("F", {}, self.ex["candidates"]), ("F", good, []),
                     ("F", good, [{"id": "a", "evidence": []}, {"id": "a", "evidence": []}]),
                     ("F", good, [{"id": "a", "evidence": [], "equivalent_to": "b"}])]:
            with self.assertRaises(ValueError):
                s.feasibility(*args, as_of=AT)


class DependsOnTests(unittest.TestCase):
    def test_changed_witness_marks_direct_and_inherited_branches(self):
        with tempfile.TemporaryDirectory() as d:
            g = Gardener(str(Path(d) / "g.sqlite"))
            try:
                ev = lambda i, op, b, parents=(), src="a" * 64, **kw: g.append(
                    event_id=i, operation=op, branch=b, actor="r", source_sha256=src, source_ref="t",
                    statement="statement " + i, at=AT, parents=parents, **kw)
                ledger.evidence(g.db, evidence_id="squad-run-1", kind="TEST_RESULT", uri="https://example.test/run1",
                                description="SQuAD replay", at=AT)
                ev("e1", "PROPOSE", "gate")
                ev("e2", "PROPOSE", "lexical", ["gate"])
                ev("e3", "PROPOSE", "threshold", ["lexical"])
                ev("e4", "PROPOSE", "llm", ["gate"], src="b" * 64)
                ev("e5", "TEST", "lexical", evidence_ids=["squad-run-1"])
                state = g.replay()
            finally:
                g.close()
        rows = query(state, depends_on="squad-run-1")["branches"]
        self.assertEqual({r["branch"]: r["dependency"] for r in rows}, {"lexical": "direct", "threshold": "inherited"})
        by_source = {r["branch"] for r in query(state, depends_on="b" * 64)["branches"]}
        self.assertEqual(by_source, {"llm"})
        self.assertNotIn("dependency", query(state)["branches"][0])
        with self.assertRaises(ValueError):
            query(state, depends_on="")


if __name__ == "__main__":
    unittest.main()
