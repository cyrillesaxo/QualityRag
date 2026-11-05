import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.activation_runtime.demo import run
from tools.activation_runtime.media import benchmark_av1


class DemoTests(unittest.TestCase):
    def test_two_independent_runs_have_identical_structural_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "one"
            second = Path(root) / "two"
            run(first)
            run(second)
            self.assertEqual((first / "receipt.json").read_bytes(), (second / "receipt.json").read_bytes())
            receipt = json.loads((first / "receipt.json").read_bytes())
            self.assertEqual(len(receipt["cases"]), 4)
            self.assertTrue(all(c["receipt"]["finite_constraint_result"] == "SAT" for c in receipt["cases"]))
            self.assertFalse(receipt["can_generate"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg integration unavailable")
class MediaTests(unittest.TestCase):
    def test_actual_lossless_av1_round_trip(self):
        encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, check=True).stdout
        if b"libaom-av1" not in encoders:
            self.skipTest("AV1 encoder unavailable")
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.mkv"
            target = Path(root) / "av1.mkv"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-n",
                            "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=4",
                            "-t", "0.5", "-c:v", "ffv1", str(source)],
                           capture_output=True, check=True, timeout=30)
            result = benchmark_av1(source, target, rights_ref="owned-generated-test-pattern",
                                   split_family="synthetic-fixture-only")
            self.assertTrue(result["yuv420p_frame_bytes_equal"])
            self.assertGreater(result["encoded_bytes"], 0)
            self.assertFalse(result["can_generate"])
            self.assertEqual(result["semantic_codex_codec"], "NOT_IMPLEMENTED")
            with self.assertRaises(ValueError):
                benchmark_av1(source, target, rights_ref="owned-generated-test-pattern", split_family="test")
