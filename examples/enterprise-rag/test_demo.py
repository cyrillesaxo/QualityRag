import importlib.util
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name("demo.py")
spec=importlib.util.spec_from_file_location("enterprise_demo",SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class TrainingExampleTest(unittest.TestCase):
    def test_missing_governing_chunks_block_generation(self):
        first, expanded=module.run()
        self.assertEqual(first["verdict"],"INCONCLUSIVE")
        self.assertEqual(expanded["verdict"],"ADMIT")
    def test_mirrored_handbook_is_not_independent(self):
        evidence=module.witnesses(["ops-7.3","ops-mirror-7.3"])
        self.assertEqual(len(evidence),2)
        self.assertEqual(len({w["origin"] for w in evidence}),1)

if __name__=="__main__":
    unittest.main()
