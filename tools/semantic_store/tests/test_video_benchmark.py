"""The benchmark must remain explicitly synthetic and reproducible."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_benchmark import SCENARIOS, make_artifact, evaluate, run
from video_catalog import write_evidence


class VideoBenchmarkTests(unittest.TestCase):
    def test_multimodal_fixture_has_more_visually_relevant_witness_hits(self):
        result=run()
        self.assertEqual(result["dataset"],"SYNTHETIC_TEXT_FIXTURES_NO_VIDEO_MEDIA")
        self.assertEqual(result["retrieval_method"],"BOUNDED_LEXICAL_ONLY")
        self.assertEqual(result["questions"],len(SCENARIOS))
        self.assertEqual(result["speech_only_hit_count"],0)
        self.assertEqual(result["multimodal_hit_count"],len(SCENARIOS))
        self.assertTrue(all(row["required_modality"]=="video" for row in result["cases"]))
        self.assertEqual(result["quality_admission"],
                         "INTEGRATION_FIXTURE_NOT_REAL_WORLD_VALIDATION")

    def test_results_are_deterministic_and_do_not_need_video_or_model(self):
        self.assertEqual(run(),run())

    def test_top_k_parameter_is_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            for item in SCENARIOS:
                write_evidence(root,make_artifact(item))
            with self.assertRaises(ValueError):
                evaluate(root=root,top_k=0)
            with self.assertRaises(ValueError):
                evaluate(root=root,top_k=31)


if __name__=="__main__":
    unittest.main()
