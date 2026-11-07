"""Video inference regression tests without downloading models or loading video."""
import hashlib
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pathlib import Path
from unittest.mock import patch

from video_evidence import VideoEvidenceError, inspect_constraints
from video_inference import (
    sample_times, compile_local_media, vision_ollama_local, media_hash,
)

class LocalVideoInferenceTests(unittest.TestCase):
    def test_sampling_regular_and_activated(self):
        times = sample_times(10000, 5000, [{"start_ms": 2500, "end_ms": 4200}], 20)
        self.assertIn(0, times)
        self.assertIn(5000, times)
        self.assertIn(2500, times)
        self.assertIn(4199, times)
        self.assertEqual(times, sorted(set(times)))

    def test_budget_fail_closed(self):
        with self.assertRaises(VideoEvidenceError):
            sample_times(10000, 250, max_frames=2)

    def test_malformed_window(self):
        with self.assertRaises(VideoEvidenceError):
            sample_times(10000, windows=[{"start_ms": 9000, "end_ms": 11000}])

    def test_no_external_network(self):
        with self.assertRaises(VideoEvidenceError):
            vision_ollama_local(b"test", model_name="vision", endpoint="https://remote.example.com")

    def test_hash_streaming(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "clip.mp4"
            p.write_bytes(b"fixture")
            self.assertEqual(media_hash(p), hashlib.sha256(b"fixture").hexdigest())

    def test_visual_pipeline_produces_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "clip.mp4"
            p.write_bytes(b"fixture")
            with patch("video_inference.probe_duration_ms", return_value=10000), patch(
                "video_inference.extract_frame", return_value=b"jpeg-bytes"
            ):
                artifact = compile_local_media(
                    p, source_id="local", revision="r1", vision_model="fixture-model",
                    interval_ms=5000, vision=lambda _: "Chair is visible.")
            self.assertEqual(len(artifact["witnesses"]), 2)
            self.assertEqual(artifact["governance"]["admission"], "INCONCLUSIVE")
            self.assertTrue(all(e["admission"] == "CANDIDATE_REQUIRES_REVIEW"
                                for e in artifact["events"]))
            self.assertEqual(inspect_constraints(artifact), [])

    def test_vision_speech_not_promoted(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "clip.mp4"
            p.write_bytes(b"fixture")
            speech = ([{"id": "s1", "modality": "audio",
                        "interval": {"start_ms": 100, "end_ms": 600},
                        "text": "The brakes are locked", "provider": "asr"}],
                      {"provider": "asr", "model": "mock"})
            with patch("video_inference.probe_duration_ms", return_value=1000), patch(
                "video_inference.asr_faster_whisper", return_value=speech
            ):
                artifact = compile_local_media(
                    p, source_id="clip", revision="1", asr_model="mock")
            self.assertEqual(artifact["events"][0]["constraints"], [])
            self.assertEqual(artifact["governance"]["semantic_interpretation"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
