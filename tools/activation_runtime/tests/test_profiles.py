import json
from pathlib import Path
import unittest
from tools.activation_runtime.common import canonical
from tools.activation_runtime.preservation import audit_output


class ProfileTests(unittest.TestCase):
    def test_distinct_profiles_protect_their_own_load_bearing_fields(self):
        root=Path(__file__).resolve().parents[1]/"profiles"
        hashes=set()
        for name,field,wrong in (("clinical-description","diagnosis","unsupported diagnosis"),
                                ("nursing","unit","g"),("legal","actor","bob"),("video","subtitle_text","GO")):
            raw=(root/name/"source.json").read_bytes()
            source=json.loads(raw)
            ir=json.loads((root/name/"ir.json").read_text())
            contract=json.loads((root/name/"contract.json").read_text())
            hashes.add(ir["source"]["sha256"])
            self.assertEqual(audit_output(raw,source,contract,current_ir=ir)["finite_constraint_result"],"SAT")
            changed={**source,field:wrong}
            self.assertEqual(audit_output(raw,changed,contract,current_ir=ir)["finite_constraint_result"],"UNSAT")
        self.assertEqual(len(hashes),4)
