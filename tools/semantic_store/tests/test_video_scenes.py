"""Model-free scene transition tests using synthetic grayscale frames."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_scenes import (
    PIXELS, luminance_frame, normalized_frame_difference, propose_change_windows,
)
from video_evidence import VideoEvidenceError


def decoder_factory(mapping):
    def run(command, **kwargs):
        at = int(float(command[command.index("-ss") + 1]) * 1000)
        return SimpleNamespace(stdout=mapping[at])
    return run


class SceneChangeTests(unittest.TestCase):
    def test_difference_is_normalized(self):
        self.assertEqual(normalized_frame_difference(bytes(PIXELS), bytes(PIXELS)), 0)
        self.assertEqual(normalized_frame_difference(bytes(PIXELS), bytes([255]) * PIXELS), 1)

    def test_change_window_from_synthetic_frames(self):
        black = bytes(PIXELS)
        white = bytes([255]) * PIXELS
        result = propose_change_windows("fixture.mp4", 5000,
                                        cadence_ms=1000, threshold=0.25,
                                        decoder=decoder_factory({
                                            0:black, 1000:black, 2000:white,
                                            3000:white, 4000:white
                                        }))
        self.assertEqual(result["receipt"]["candidate_transition_count"], 1)
        self.assertEqual(result["windows"][0]["start_ms"], 1400)
        self.assertEqual(result["windows"][0]["end_ms"], 2601)
        self.assertEqual(result["receipt"]["interpretation"], "UNVERIFIED_CHANGE_POINT")

    def test_scene_budget_rejects_excess_probes(self):
        with self.assertRaises(VideoEvidenceError):
            propose_change_windows("fixture.mp4", 9000, cadence_ms=1000, max_probes=3)

    def test_gradual_no_change_is_not_absence_proof(self):
        static = bytes([40]) * PIXELS
        result = propose_change_windows("fixture.mp4", 3000, cadence_ms=1000,
                                        decoder=decoder_factory({0:static, 1000:static, 2000:static}))
        self.assertEqual(result["windows"], [])
        self.assertEqual(result["receipt"]["interpretation"], "UNVERIFIED_CHANGE_POINT")

    def test_decode_wrong_size_fails_closed(self):
        with self.assertRaises(VideoEvidenceError):
            luminance_frame("fixture.mp4", 0, decoder=lambda *a, **k: SimpleNamespace(stdout=b"bad"))

    def test_sampler_includes_scene_window_but_keeps_unverified(self):
        import tempfile
        from video_inference import compile_local_media
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            path.write_bytes(b"fixture")
            proposed = {"windows":[{"start_ms":1000,"end_ms":3000,"peak_difference":1.0}],
                        "receipt":{"detector":"synthetic","interpretation":"UNVERIFIED_CHANGE_POINT"}}
            with patch("video_inference.probe_duration_ms", return_value=6000), patch(
                "video_inference.propose_change_windows", return_value=proposed
            ), patch("video_inference.extract_frame", return_value=b"image"):
                artifact = compile_local_media(
                    path, source_id="test", revision="1", vision_model="mock",
                    detect_scene_changes=True, interval_ms=3000, max_frames=20,
                    vision=lambda frame: "Possible wheelchair in image")
            self.assertGreater(len(artifact["witnesses"]), 2)
            self.assertEqual(artifact["governance"]["admission"], "INCONCLUSIVE")
            self.assertTrue(any(r.get("detector") == "synthetic" for r in artifact["model_receipts"]))


if __name__ == "__main__":
    unittest.main()
