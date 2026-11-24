import tempfile
import unittest
from pathlib import Path
from tools.activation_runtime.pedagogical_evolution import ARMS, describe_pedagogical_cycle, record_pedagogical_cycle
from tools.activation_runtime.gardener import Gardener
from tools.activation_runtime.artifacts import ArtifactStore

P="a"*64
R="b"*64
NOW="2026-01-01T00:00:00Z"
def report():
    return {"studyDesign":"EXPERIENTIAL_COMPARISON","primaryOutcome":"delayed_transfer_per_learning_minute",
            "outcomeKind":"simulated","promotionAuthorized":False,"protocolId":"fixture",
            "comparableMaterials":True,"arms":[{"arm":a,"assigned":2,"delayedAssessed":1,
            "missingDelayed":1,"meanDelayedTransferPerMinute":0.0,"individualOutcomes":[{"id":"private"}]} for a in ARMS]}

class PedagogicalTests(unittest.TestCase):
    def test_aggregate_only_and_no_promotion(self):
        x=describe_pedagogical_cycle(report(),protocol_sha256=P,representation_sha256=R)
        self.assertFalse(x["can_promote"])
        self.assertIsNone(x["selected"])
        self.assertIn("SIMULATED_ONLY",x["blockers"])
        self.assertIn("INCOMPLETE_FOLLOWUP_OR_ARM",x["blockers"])
        self.assertNotIn("private",str(x))
        self.assertEqual(x["arms"]["standard"]["rate"],0.0)
    def test_invalid_denominators(self):
        data=report()
        data["arms"][0]["missingDelayed"]=0
        with self.assertRaises(ValueError):describe_pedagogical_cycle(data,protocol_sha256=P,representation_sha256=R)
    def test_ledger_replay_and_revision_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=Gardener(Path(tmp)/"research.db")
            try:
                store=ArtifactStore(Path(tmp)/"objects",tenant="research")
                g.append(event_id="hypothesis",operation="PROPOSE",branch="pedagogy",actor="researcher",
                         source_sha256=R,source_ref="fixture",statement="Compare representations",at=NOW)
                args=dict(branch="pedagogy",actor="researcher",at=NOW,report=report(),protocol_sha256=P,representation_sha256=R)
                first=record_pedagogical_cycle(g,store,**args)
                self.assertEqual(first,record_pedagogical_cycle(g,store,**args))
                self.assertEqual(len(g.replay()["events"]),2)
                self.assertEqual(g.replay()["branches"]["pedagogy"]["evidence_status"],"UNVERIFIED")
                with self.assertRaises(ValueError):record_pedagogical_cycle(g,store,**{**args,"representation_sha256":"c"*64})
            finally:g.close()
if __name__=="__main__":unittest.main()
