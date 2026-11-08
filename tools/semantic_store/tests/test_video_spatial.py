"""Bounded local spatial proposals and geometric track integration tests."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_spatial import validate_spatial_proposals, frame_detections, detect_objects_ollama_local
from video_inference import compile_local_media
from video_evidence import VideoEvidenceError, inspect_constraints


def proposal(x=0.1, label="wheelchair", state="unknown"):
    return {"category": label, "bbox": [x, 0.1, x + 0.3, 0.6],
            "attributes": {"brake_position": state}}


class SpatialTests(unittest.TestCase):
    def test_valid_spatial_proposals(self):
        result = validate_spatial_proposals({"objects": [proposal()]})
        self.assertEqual(result[0]["category"], "wheelchair")
        self.assertEqual(frame_detections(result, "frame-0")[0]["witness_id"], "frame-0")

    def test_missing_or_extra_schema_fails_closed(self):
        for item in ({"bbox": [0.1, 0.2, 0.4, 0.5], "attributes": {}},
                     {**proposal(), "identity": "person"}):
            with self.subTest(item=item), self.assertRaises(VideoEvidenceError):
                validate_spatial_proposals({"objects": [item]})

    def test_bad_coordinates_rejected(self):
        for box in ([0.8, 0.1, 0.3, 0.5], [-0.1,0,0.2,0.2],
                    [0.1,0.2,float("nan"),0.8], [True,0,0.2,0.2]):
            with self.subTest(box=box), self.assertRaises(VideoEvidenceError):
                validate_spatial_proposals({"objects": [{**proposal(), "bbox": box}]})

    def test_duplicates_rejected(self):
        with self.assertRaises(VideoEvidenceError):
            validate_spatial_proposals({"objects": [proposal(), proposal()]})

    def test_budget_rejected(self):
        with self.assertRaises(VideoEvidenceError):
            validate_spatial_proposals({"objects": [proposal(i/100) for i in range(21)]})

    def test_external_endpoint_rejected(self):
        with self.assertRaises(VideoEvidenceError):
            detect_objects_ollama_local(b"jpg", model_name="mock",
                                         endpoint="https://example.com")

    def test_auto_detection_integrates_candidate_tracking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            path.write_bytes(b"fixture")
            attributes = iter(["not_visible", "appears_engaged"])
            with patch("video_inference.probe_duration_ms", return_value=10000), patch(
                "video_inference.extract_frame", side_effect=[b"jpeg1", b"jpeg2"]
            ):
                artifact = compile_local_media(
                    path, source_id="clip", revision="1", vision_model="mock",
                    auto_detect_objects=True, interval_ms=5000,
                    vision=lambda _: "wheelchair visible",
                    spatial_detect=lambda _: [proposal(state=next(attributes))])
            self.assertEqual(artifact["governance"]["admission"], "INCONCLUSIVE")
            tracks = [e for e in artifact["events"] if e["id"].startswith("track-")]
            self.assertEqual(len(tracks), 1)
            self.assertEqual(tracks[0]["changes"][0]["status"], "CHANGED")
            self.assertEqual(tracks[0]["constraints"][0]["state"], "UNKNOWN")
            self.assertIn("object_continuity_verified",
                          [c["constraint"] for c in inspect_constraints(artifact)])

    def test_auto_and_manual_detection_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            path.write_bytes(b"fixture")
            with patch("video_inference.probe_duration_ms", return_value=1000), patch(
                "video_inference.extract_frame", return_value=b"jpeg"
            ):
                with self.assertRaises(VideoEvidenceError):
                    compile_local_media(
                        path, source_id="clip", revision="1", vision_model="mock",
                        auto_detect_objects=True, detections=[],
                        vision=lambda _: "wheelchair", spatial_detect=lambda _: [])


if __name__ == "__main__":
    unittest.main()
