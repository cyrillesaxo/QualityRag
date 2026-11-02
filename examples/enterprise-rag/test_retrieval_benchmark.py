import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location("benchmark",Path(__file__).with_name("retrieval_benchmark.py"))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class BenchmarkTest(unittest.TestCase):
 def test_ranking_and_decision(self):
  generic,targeted,first,second=b.run()
  self.assertEqual(first["verdict"],"INCONCLUSIVE")
  self.assertIn("annex-d-187",targeted)
 def test_ranking_is_deterministic(self):
  self.assertEqual(b.rank("automated recovery after timeout"),b.rank("automated recovery after timeout"))
if __name__=="__main__":unittest.main()
