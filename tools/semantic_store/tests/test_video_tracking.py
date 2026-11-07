"""Candidate-only geometric track association and attribute history tests."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_evidence import VideoEvidenceError, inspect_constraints
from video_tracking import associate_detections, intersection_over_union, track_events
from video_inference import compile_local_media


def witness(identifier, at):
    return {"id": identifier, "modality": "video",
            "interval": {"start_ms": at, "end_ms": at+1},
            "frame_sha256": hashlib.sha256(identifier.encode()).hexdigest()}


def detection(wid, box=None, *, attr="open", category="door"):
    return {"witness_id": wid, "category": category,
            "bbox": box or [0.1, 0.1, 0.4, 0.5],
            "attributes": {"position": attr}}


class TrackingTests(unittest.TestCase):
    def test_identical_boxes_associate_but_not_verify(self):
        ws = [witness("a", 0), witness("b", 1000), witness("c", 2000)]
        tracks = associate_detections([
            detection("a", attr="closed"), detection("b", attr="closed"),
            detection("c", attr="open")], ws)
        self.assertEqual(len(tracks), 1)
        self.assertFalse(tracks[0]["identity_verified"])
        self.assertEqual([x["status"] for x in tracks[0]["changes"]],
                         ["UNCHANGED", "CHANGED"])
        self.assertEqual(tracks[0]["changes"][1]["verification"], "UNVERIFIED_CANDIDATE")
        self.assertEqual(track_events(tracks)[0]["constraints"][0]["state"], "UNKNOWN")

    def test_no_match_after_gap(self):
        ws = [witness("a", 0), witness("b", 9000)]
        tracks = associate_detections([detection("a"), detection("b")], ws)
        self.assertEqual(len(tracks), 2)
        self.assertEqual(track_events(tracks), [])

    def test_no_merge_for_similar_classes_in_distinct_locations(self):
        ws = [witness("a", 0), witness("b", 1000)]
        tracks = associate_detections([
            detection("a", [0.1,0.1,0.3,0.3]),
            detection("b", [0.6,0.6,0.9,0.9])], ws)
        self.assertEqual(len(tracks), 2)

    def test_hard_cut_prevents_false_track_continuity(self):
        ws = [witness("a", 0), witness("b", 1000)]
        tracks = associate_detections(
            [detection("a"), detection("b")], ws, scene_cut_ms=[500])
        self.assertEqual(len(tracks), 2)
        self.assertEqual(track_events(tracks), [])

    def test_scene_cut_configuration_rejects_non_integer(self):
        ws = [witness("a", 0), witness("b", 1000)]
        with self.assertRaises(VideoEvidenceError):
            associate_detections([detection("a"), detection("b")],
                                 ws, scene_cut_ms=["500"])

    def test_different_categories_never_merge(self):
        ws = [witness("a", 0), witness("b", 1000)]
        tracks = associate_detections([
            detection("a", category="chair"), detection("b", category="bed")], ws)
        self.assertEqual(len(tracks), 2)

    def test_ambiguous_association_abstains(self):
        ws = [witness("a", 0), witness("b", 0), witness("c", 1000)]
        boxes = [[0.1,0.1,0.6,0.6], [0.2,0.1,0.7,0.6], [0.15,0.1,0.65,0.6]]
        tracks = associate_detections([
            detection("a", boxes[0]), detection("b", boxes[1]),
            detection("c", boxes[2])], ws, min_iou=0.5, ambiguity_margin=0.15)
        self.assertEqual(len(tracks), 3)

    def test_missing_attribute_is_unknown_not_changed(self):
        ws = [witness("a", 0), witness("b", 1000)]
        second = detection("b")
        second["attributes"] = {}
        tracks = associate_detections([detection("a"), second], ws)
        self.assertEqual(tracks[0]["changes"][0]["status"], "UNKNOWN")

    def test_no_duplicate_detection(self):
        ws = [witness("a", 0)]
        with self.assertRaises(VideoEvidenceError):
            associate_detections([detection("a"), detection("a")], ws)

    def test_no_unhashed_witness(self):
        ws = [witness("a", 0)]
        ws[0].pop("frame_sha256")
        with self.assertRaises(VideoEvidenceError):
            associate_detections([detection("a")], ws)

    def test_invalid_box_rejected(self):
        with self.assertRaises(VideoEvidenceError):
            intersection_over_union([0.7,0.6,0.2,0.9], [0.1,0.2,0.4,0.5])

    def test_inference_integrates_track_with_unknown_constraint(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "clip.mp4"
            path.write_bytes(b"fixture")
            with patch("video_inference.probe_duration_ms", return_value=10000), patch(
                "video_inference.extract_frame", side_effect=[b"before", b"after"]
            ):
                artifact = compile_local_media(
                    path, source_id="test", revision="1", vision_model="mock",
                    interval_ms=5000, vision=lambda _: "Chair visible",
                    detections=[detection("frame-0", attr="closed"),
                                detection("frame-1", attr="open")])
            event = next(e for e in artifact["events"] if e["id"] == "track-candidate-track-0")
            self.assertEqual(event["changes"][0]["status"], "CHANGED")
            self.assertEqual(event["constraints"][0]["state"], "UNKNOWN")
            self.assertEqual(artifact["governance"]["admission"], "INCONCLUSIVE")
            self.assertEqual(inspect_constraints(artifact)[0]["constraint"],
                             "object_continuity_verified")


if __name__ == "__main__":
    unittest.main()
