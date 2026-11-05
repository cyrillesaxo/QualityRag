import json
from pathlib import Path
import subprocess
import sys
import unittest
from tools.activation_runtime.agents import propose,research_round,ROLES,schedule


class AgentTests(unittest.TestCase):
    def test_actual_syscall_sandbox_denies_file_network_and_fork(self):
        worker=Path(__file__).resolve().parents[1]/"agent_worker.py"
        request={"budget":{"cpu_seconds":2,"memory_bytes":128000000}}
        result=subprocess.run([sys.executable,str(worker),"--probe"],input=json.dumps(request).encode(),capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["sandbox_denied"],{"file_open":True,"socket":True,"fork":True})

    def test_six_real_parallel_roles_disagree_and_do_not_promote(self):
        tasks={r:{} for r in ROLES}
        tasks["packspec-guardian"]={"required_fields":["NOT","unit"],"preserved_fields":["unit"]}
        tasks["counterexample"]={"cases":[{"id":"negation","source":"NOT","candidate":""}]}
        result=research_round({"schema":"finite-grammar/v1"},tasks)
        self.assertTrue(all(v["status"]=="PROPOSAL" for v in result["results"].values()),result)
        self.assertEqual(result["decision"],"BLOCK")
        self.assertTrue(result["disagreement"])
        self.assertFalse(result["can_promote"])

    def test_input_budgets_and_unknown_operators(self):
        with self.assertRaises(ValueError):
            propose("shell",parent_grammar={},task={})
        with self.assertRaises(ValueError):
            propose("decomposition",parent_grammar={},task={"data":"x"*1000},input_token_limit=1)
        result=propose("decomposition",parent_grammar={},task={},memory_bytes=1)
        self.assertEqual(result["status"],"UNKNOWN")

    def test_expected_work_scheduler_stops_at_budget(self):
        result=schedule([{"id":"a","expected_value":10,"cost":2},
                         {"id":"b","expected_value":1,"cost":3}],budget=2)
        self.assertEqual(result["selected"],["a"])
        self.assertEqual(result["remaining_budget"],0)
