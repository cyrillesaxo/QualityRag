import unittest

import labeled_pipeline as lp
from qualityrag.labeling import LexicalLabeler


class LabeledPipelineTest(unittest.TestCase):
    def test_lexical_labels_reproduce_hand_label_verdict(self):
        report = lp.run(LexicalLabeler(0.6))
        self.assertEqual(report["verdict"], report["hand_label_verdict"])

    def test_strict_threshold_abstains(self):
        report = lp.run(LexicalLabeler(1.0))
        self.assertEqual(report["verdict"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
