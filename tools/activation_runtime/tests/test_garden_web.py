"""Exercise the console's tree layout/replay code (web/garden.js) in Node on a real replayed garden."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.activation_runtime.gardener import Gardener

WEB = Path(__file__).resolve().parents[1] / "web"
AT = "2026-11-05T12:00:00Z"
SCRIPT = r"""
const G = require(process.argv[process.argv.length - 1]);
const state = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const head = state.head_sequence;
const out = {
  pos: G.layout(state),
  atHead: G.computeAt(state, head),
  atFive: G.computeAt(state, 5),
  atZero: G.scene(state, 0).nodes.length,
  scene: G.scene(state, head, {matches: ['llm'], selected: 'llm'}),
  again: G.scene(state, head, {matches: ['llm'], selected: 'llm'})
};
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node unavailable")
class GardenWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as d:
            g = Gardener(str(Path(d) / "g.sqlite"))
            ev = lambda i, op, b, parents=(): g.append(event_id=i, operation=op, branch=b, actor="r", source_sha256="a" * 64,
                                                      source_ref="turn:" + i, statement="statement " + i, at=AT, parents=parents)
            ev("e1", "PROPOSE", "gate")
            ev("e2", "PROPOSE", "lexical", ["gate"])
            ev("e3", "PROPOSE", "llm", ["gate"])
            ev("e4", "PROPOSE", "roots", ["gate"])
            ev("e5", "CHALLENGE", "lexical")
            ev("e6", "PRUNE", "lexical")
            ev("e7", "PROPOSE", "dupes", ["llm"])
            ev("e8", "SYNTHESIZE", "shared", ["llm", "dupes"])
            ev("e9", "CHALLENGE", "llm")
            ev("e10", "REOPEN", "lexical")
            state = g.replay()
            g.close()
        run = subprocess.run(["node", "-e", SCRIPT, "--", str(WEB / "garden.js")], input=json.dumps(state),
                             capture_output=True, text=True, timeout=30)
        if run.returncode:
            raise AssertionError(run.stderr)
        cls.out = json.loads(run.stdout)

    def test_layout_grows_upward_and_stays_in_view(self):
        pos = self.out["pos"]
        self.assertEqual(set(pos), {"gate", "lexical", "llm", "roots", "dupes", "shared"})
        for name, p in pos.items():
            self.assertTrue(0 <= p["x"] <= 1000 and 0 <= p["y"] <= 760, name)
        for child, parent in (("lexical", "gate"), ("llm", "gate"), ("dupes", "llm")):
            self.assertLess(pos[child]["y"], pos[parent]["y"])
        self.assertLess(pos["shared"]["y"], pos["dupes"]["y"])  # a synthesis sits above all its parents
        self.assertEqual(pos["shared"]["depth"], 3)

    def test_replay_reconstructs_each_moment(self):
        five, head = self.out["atFive"], self.out["atHead"]
        self.assertFalse(five["dupes"]["visible"])
        self.assertTrue(five["lexical"]["open"] and five["lexical"]["active"])
        self.assertTrue(head["lexical"]["active"] and head["lexical"]["reopened"])
        self.assertTrue(head["llm"]["open"])
        self.assertEqual(self.out["atZero"], 0)

    def test_scene_marks_matches_selection_and_is_deterministic(self):
        nodes = {n["name"]: n for n in self.out["scene"]["nodes"]}
        self.assertEqual(nodes["llm"]["dim"], 1)
        self.assertLess(nodes["gate"]["dim"], 1)
        self.assertTrue(nodes["llm"]["selected"])
        self.assertEqual(nodes["llm"]["meta"], "open challenge")
        dashed = [e for e in self.out["scene"]["edges"] if e["to"] == "shared" and e["dash"]]
        self.assertEqual(len(dashed), 1)  # the second synthesis parent is drawn as a merging limb
        self.assertEqual(self.out["scene"], self.out["again"])
        self.assertTrue(self.out["scene"]["decor"])


if __name__ == "__main__":
    unittest.main()
