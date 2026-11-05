import copy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import unittest
from tools.activation_runtime.agents import ROLES,propose,evaluation_pin
from tools.activation_runtime.common import fingerprint


class AgentPinTests(unittest.TestCase):
    def test_every_role_has_patches_rationale_and_exact_evaluation_pin(self):
        parent={"version":1}
        for role in ROLES:
            with self.subTest(role=role):
                result=propose(role,parent_grammar=parent,task={})
                self.assertEqual(result["status"],"PROPOSAL",result)
                p=result["proposal"]
                self.assertEqual(p["parent_grammar_sha256"],fingerprint(parent))
                self.assertIsInstance(p["patches"],list)
                self.assertTrue(p["rationale"])
                self.assertEqual(p["evaluation_pin"],evaluation_pin(role,{}))
                self.assertFalse(p["can_generate"])

    def test_worker_rejects_changed_dataset_and_each_stale_code_pin(self):
        task={"obligations":["NOT"]};role="decomposition"
        request={"schema":"qualityrag.agent-request/v1","role":role,
            "parent_grammar_sha256":fingerprint({}),"task":task,"evaluation_pin":evaluation_pin(role,task),
            "budget":{"cpu_seconds":2,"memory_bytes":128000000}}
        worker=Path(__file__).resolve().parents[1]/"agent_worker.py"
        def execute(value):
            return subprocess.run([sys.executable,str(worker)],input=json.dumps(value).encode(),
                                  capture_output=True,timeout=5)
        self.assertEqual(execute(request).returncode,0)
        changed=copy.deepcopy(request);changed["task"]["obligations"]=["YES"]
        self.assertNotEqual(execute(changed).returncode,0)
        for name in request["evaluation_pin"]["code_sha256"]:
            changed=copy.deepcopy(request);changed["evaluation_pin"]["code_sha256"][name]="0"*64
            with self.subTest(source=name):self.assertNotEqual(execute(changed).returncode,0)
        changed=copy.deepcopy(request);del changed["evaluation_pin"]
        self.assertNotEqual(execute(changed).returncode,0)

    def test_pin_records_actual_source_bytes_and_exact_task_dataset(self):
        task={"obligations":["é NOT"]};pin=evaluation_pin("decomposition",task)
        self.assertEqual(pin["dataset_sha256"],fingerprint(task))
        root=Path(__file__).resolve().parents[1]
        for name,digest in pin["code_sha256"].items():
            self.assertEqual(digest,sha256((root/name).read_bytes()).hexdigest())
        self.assertNotEqual(pin["dataset_sha256"],evaluation_pin("decomposition",{})["dataset_sha256"])
