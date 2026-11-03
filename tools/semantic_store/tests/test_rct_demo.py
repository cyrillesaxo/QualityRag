"""The documented one-command integration demo must remain fail-closed."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_demo import run_demo


class DemoContractTest(unittest.TestCase):
    def test_end_to_end_demo_contract(self):
        output=run_demo()
        self.assertEqual(output["status"],"STRUCTURAL_CHECKS_PASS")
        self.assertEqual(output["finite_relation_verdict"],"SAT")
        self.assertEqual(output["source_facts"]-output["active_lens_facts"],3)
        self.assertTrue(output["canonical_source_reconstructed"])
        self.assertFalse(output["native_ff_rct"])
        self.assertFalse(output["can_generate"])
        self.assertEqual(output["qualityrag_admission"],"INCONCLUSIVE")

    def test_documented_cli_is_executable(self):
        script=Path(__file__).resolve().parents[1] / "rct_demo.py"
        result=subprocess.run([sys.executable,str(script)],capture_output=True,
                              text=True,check=True,timeout=30)
        output=json.loads(result.stdout)
        self.assertEqual(output["schema"],"rct.reproducible-demo/v2")
        self.assertEqual(output["qualityrag_admission"],"INCONCLUSIVE")


if __name__=="__main__":
    unittest.main()
