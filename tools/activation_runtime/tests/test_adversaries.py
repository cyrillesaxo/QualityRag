import tempfile
import unittest
from tools.activation_runtime.adversaries import corpus,challenge
from tools.activation_runtime.common import fingerprint
from tools.activation_runtime.neural_baseline import benchmark


class AdversarialTests(unittest.TestCase):
    def test_all_distinctions_and_optimistic_evaluator_block(self):
        result=challenge(lambda a,b:"SAT" if fingerprint(a)==fingerprint(b) else "UNSAT",corpus())
        self.assertEqual(result["false_accept_rate"],0)
        self.assertEqual(result["missed_counterexample_rate"],0)
        bad=challenge(lambda a,b:"SAT",corpus())
        self.assertEqual(bad["promotion"],"BLOCK")
        self.assertGreater(bad["critical_regressions"],0)

    def test_no_fake_neural_baseline_without_licensed_weights(self):
        with self.assertRaises(ValueError):
            benchmark("source",checkpoint="/missing/model",checkpoint_sha256="a"*64,license_ref="none")
