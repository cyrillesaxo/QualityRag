from pathlib import Path
import tempfile
import unittest
from tools.activation_runtime.gardener import Gardener
from tools.activation_runtime.proposals import suggest,record_outcome,dependency_evidence


class ProposalTests(unittest.TestCase):
    def test_source_bound_suggestions_feedback_metrics_and_uncertainty(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"garden.sqlite"
            garden=Gardener(path)
            try:
                for i in (1,2):
                    garden.append(event_id="event"+str(i),operation="PROPOSE",branch="branch"+str(i),actor="proposer",
                        source_sha256="a"*64,source_ref="turn:1",statement="Same hypothesis",at="2026-11-04T12:00:00Z")
                state=garden.append(event_id="event3",operation="SYNTHESIZE",branch="synth",actor="proposer",
                    source_sha256="a"*64,source_ref="turn:1",statement="Synthesis",at="2026-11-04T12:00:00Z",
                    parents=["branch1","branch2"])
                self.assertEqual(dependency_evidence(state)["synth"],"UNRESOLVED_DEPENDENCIES")
            finally:garden.close()
            result=suggest(path)
            self.assertEqual(len(result["proposals"]),1)
            self.assertIsNone(result["proposals"][0]["confidence"])
            record_outcome(path,proposal_id=result["proposals"][0]["id"],actor="reviewer",
                           verdict="INCORRECT",useful=False,elapsed_ms=50,false_merge=True)
            metrics=suggest(path)["metrics"]
            self.assertEqual(metrics["false_merge_rate"],1)
            self.assertEqual(metrics["reported_useful_rate"],0)

    def test_challenge_clears_after_test_and_reopens_on_new_challenge(self):
        import ledger
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"garden.sqlite"
            garden=Gardener(path)
            ev=lambda i,op,**kw:garden.append(event_id=i,operation=op,branch="b",actor="r",source_sha256="a"*64,
                source_ref="turn:"+i,statement="Statement "+i,at="2026-11-04T12:00:00Z",**kw)
            try:
                ev("e1","PROPOSE");ev("e2","CHALLENGE")
            finally:garden.close()
            self.assertEqual([p["kind"] for p in suggest(path)["proposals"]],["UNRESOLVED_CHALLENGE"])
            garden=Gardener(path)
            try:
                ledger.evidence(garden.db,evidence_id="run1",kind="TEST_RESULT",uri="https://example.test/run1",
                                description="Host-recorded test",at="2026-11-04T12:00:00Z")
                ev("e3","TEST",evidence_ids=["run1"])
            finally:garden.close()
            self.assertEqual(suggest(path)["proposals"],[])
            garden=Gardener(path)
            try:ev("e4","CHALLENGE")
            finally:garden.close()
            reopened=suggest(path)["proposals"]
            self.assertEqual([p["kind"] for p in reopened],["UNRESOLVED_CHALLENGE"])
            self.assertEqual(reopened[0]["source_ref"],"turn:e4")

    def test_pruned_branch_challenge_not_suggested(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"garden.sqlite"
            garden=Gardener(path)
            ev=lambda i,op:garden.append(event_id=i,operation=op,branch="b",actor="r",source_sha256="a"*64,
                source_ref="turn:"+i,statement="Statement "+i,at="2026-11-04T12:00:00Z")
            try:ev("e1","PROPOSE");ev("e2","CHALLENGE");ev("e3","PRUNE")
            finally:garden.close()
            self.assertEqual(suggest(path)["proposals"],[])

