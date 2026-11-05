import tempfile
import unittest
from pathlib import Path

from tools.activation_runtime.gardener import Gardener, query

AT = "2026-11-05T12:00:00Z"


class GardenQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.garden = Gardener(str(Path(self.temp.name) / "g.sqlite"))
        self.addCleanup(self.garden.close)
        ev = self.ev
        ev("e1", "PROPOSE", "gate", "A deterministic evidence gate stops unsupported answers")
        ev("e2", "PROPOSE", "lexical", "Word overlap is a sufficient labeler", parents=["gate"])
        ev("e3", "PROPOSE", "llm", "An LLM labeler with exact-quote grounding", parents=["gate"])
        ev("e4", "CHALLENGE", "lexical", "Adversarial questions reuse passage wording")
        ev("e5", "PRUNE", "lexical", "Not viable alone")
        ev("e6", "PROPOSE", "dupes", "Duplicates are two-way entailment", parents=["llm"])
        ev("e7", "CHALLENGE", "llm", "A self-abstaining LLM may match the gate")

    def ev(self, eid, op, branch, statement, parents=()):
        return self.garden.append(event_id=eid, operation=op, branch=branch, actor="r", source_sha256="a" * 64,
                                  source_ref="turn:" + eid, statement=statement, at=AT, parents=parents)

    def q(self, **kw):
        return query(self.garden.replay(), **kw)

    def names(self, result):
        return [b["branch"] for b in result["branches"]]

    def test_sequences_and_head(self):
        state = self.garden.replay()
        self.assertEqual(state["head_sequence"], 7)
        self.assertEqual([state["events"][e]["sequence"] for e in state["order"]], list(range(1, 8)))

    def test_filters(self):
        self.assertEqual(self.names(self.q()), ["gate", "lexical", "llm", "dupes"])
        self.assertEqual(self.names(self.q(text="ENTAILMENT")), ["dupes"])
        self.assertEqual(self.names(self.q(text="passage wording")), ["lexical"])  # matches later events too
        self.assertEqual(self.names(self.q(active=False)), ["lexical"])
        self.assertEqual(self.names(self.q(open_challenge=True)), ["lexical", "llm"])
        self.assertEqual(self.names(self.q(open_challenge=True, active=True)), ["llm"])
        self.assertEqual(self.names(self.q(evidence_status="UNVERIFIED")), ["gate", "lexical", "llm", "dupes"])
        self.assertEqual(self.names(self.q(evidence_status="VALIDATED")), [])

    def test_lineage_and_shape(self):
        self.assertEqual(self.names(self.q(lineage_of="llm")), ["gate", "llm", "dupes"])
        row = next(b for b in self.q()["branches"] if b["branch"] == "llm")
        self.assertEqual((row["parents"], row["children"], row["events"], row["created_sequence"], row["last_sequence"]),
                         (["gate"], ["dupes"], 2, 3, 7))
        self.assertEqual(row["statement"], "An LLM labeler with exact-quote grounding")

    def test_growth_feed(self):
        result = self.q(since=5)
        self.assertEqual([e["event_id"] for e in result["events"]], ["e6", "e7"])
        self.assertEqual(result["head_sequence"], 7)
        self.assertEqual(self.q(since=7)["events"], [])
        self.ev("e8", "PROPOSE", "shared", "One labeler serves gate and Gardener", parents=["llm"])
        self.assertEqual([e["event_id"] for e in self.q(since=7)["events"]], ["e8"])

    def test_limit_and_validation(self):
        result = self.q(limit=2)
        self.assertEqual((len(result["branches"]), result["total"], result["truncated"]), (2, 4, True))
        for bad in ({"limit": 0}, {"limit": 501}, {"since": -1}, {"since": True}, {"active": "yes"},
                    {"text": "x" * 201}, {"lineage_of": "missing"}, {"evidence_status": 3}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.q(**bad)
        self.assertEqual(self.q()["independent_validation"], "NOT_ESTABLISHED")


if __name__ == "__main__":
    unittest.main()
