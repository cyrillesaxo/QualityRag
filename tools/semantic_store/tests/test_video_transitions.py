"""Paired-frame semantic transition candidate regressions; zero model downloads."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_evidence import VideoEvidenceError, inspect_constraints
from video_inference import compile_local_media
from video_transitions import validate_transition, propose_visual_transitions


def witness(name, time_ms, data):
    return {"id": name, "modality": "video",
            "interval": {"start_ms": time_ms, "end_ms": time_ms + 1},
            "frame_sha256": hashlib.sha256(data).hexdigest()}


def comparison(status="UNKNOWN"):
    return {"entity": "wheelchair", "attribute": "brake position",
            "before": "uncertain", "after": "uncertain", "status": status}


class TransitionTests(unittest.TestCase):
    def test_candidate_preserves_uncertainty(self):
        a, b = witness("first", 100, b"a"), witness("second", 300, b"b")
        result = validate_transition(comparison(), a, b)
        self.assertEqual(result["evidence_status"], "UNVERIFIED_CANDIDATE")
        self.assertEqual(result["physical_constraint_verdict"], "UNKNOWN")
        self.assertEqual(result["interval"], {"start_ms": 100, "end_ms": 301})

    def test_changed_is_not_verified(self):
        result = validate_transition(comparison("CHANGED"),
                                     witness("a", 0, b"a"), witness("b", 10, b"b"))
        self.assertEqual(result["status"], "CHANGED")
        self.assertEqual(result["causal_attribution"], "UNKNOWN")

    def test_invalid_model_schema_rejected(self):
        with self.assertRaises(VideoEvidenceError):
            validate_transition({"action": "brakes locked"},
                                witness("a", 0, b"a"), witness("b", 10, b"b"))

    def test_hash_tampering_rejected(self):
        frames = [(witness("a", 0, b"original"), b"tampered"),
                  (witness("b", 10, b"second"), b"second")]
        with self.assertRaises(VideoEvidenceError):
            propose_visual_transitions([(frames[0], frames[1])],
                                       compare=lambda a, b: comparison())

    def test_reversed_order_rejected(self):
        with self.assertRaises(VideoEvidenceError):
            validate_transition(comparison(),
                                witness("new", 500, b"new"),
                                witness("old", 100, b"old"))

    def test_pair_budget_rejected(self):
        with self.assertRaises(VideoEvidenceError):
            propose_visual_transitions([None, None], compare=lambda a, b: comparison(),
                                       max_pairs=1)

    def test_inference_produces_unverified_transition_event(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "clip.mp4"
            file.write_bytes(b"fixture")
            with patch("video_inference.probe_duration_ms", return_value=10000), patch(
                "video_inference.extract_frame", side_effect=[b"before", b"after"]
            ):
                artifact = compile_local_media(
                    file, source_id="clip", revision="r1", vision_model="mock",
                    interval_ms=5000, detect_transitions=True,
                    vision=lambda img: "Possible chair",
                    transition_compare=lambda a, b: comparison("CHANGED"))
            candidate = next(e for e in artifact["events"] if e["id"] == "transition-0")
            self.assertEqual(candidate["witnesses"], ["frame-0", "frame-1"])
            self.assertEqual(candidate["changes"][0]["physical_constraint_verdict"], "UNKNOWN")
            self.assertEqual(candidate["constraints"][0]["state"], "UNKNOWN")
            self.assertEqual(artifact["governance"]["admission"], "INCONCLUSIVE")
            self.assertEqual(inspect_constraints(artifact)[0]["constraint"], "transition_verified")

    def test_inference_pair_cap_prevents_processing(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "clip.mp4"
            file.write_bytes(b"fixture")
            with patch("video_inference.probe_duration_ms", return_value=10000), patch(
                "video_inference.extract_frame"
            ) as extract:
                with self.assertRaises(VideoEvidenceError):
                    compile_local_media(
                        file, source_id="clip", revision="r1", vision_model="mock",
                        interval_ms=1000, detect_transitions=True,
                        max_transition_pairs=2, vision=lambda img: "Chair",
                        transition_compare=lambda a,b: comparison())
                extract.assert_not_called()


if __name__ == "__main__":
    unittest.main()
