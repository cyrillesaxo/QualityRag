"""Regression tests for candidate-only multimodal evidence."""
import hashlib
import unittest

from video_evidence import compile_video_evidence, inspect_constraints, VideoEvidenceError

HASH = hashlib.sha256(b"fixture-video").hexdigest()
FRAME = hashlib.sha256(b"fixture-frame").hexdigest()


def fixture():
    return dict(source_id="clip-1", revision="1", media_sha256=HASH,
                duration_ms=10000, witnesses=[
                    dict(id="speech", modality="audio", interval={"start_ms": 1000, "end_ms": 4000},
                         text="Lock the wheelchair", provider="asr"),
                    dict(id="frame", modality="video", interval={"start_ms": 2000, "end_ms": 5000},
                         text="Wheelchair visible", provider="vision",
                         frame_sha256=FRAME, region=[0.1, 0.1, 0.9, 0.9])],
                events=[dict(id="transfer", label="wheelchair transfer",
                             interval={"start_ms": 1000, "end_ms": 6000},
                             witnesses=["speech", "frame"],
                             constraints=[dict(name="brakes_engaged", state="UNKNOWN", witnesses=["frame"])])])


class VideoEvidenceTests(unittest.TestCase):
    def test_unknown_is_retained(self):
        result = compile_video_evidence(**fixture())
        self.assertEqual(result["governance"]["admission"], "INCONCLUSIVE")
        self.assertEqual(inspect_constraints(result)[0]["state"], "UNKNOWN")

    def test_deterministic_fingerprint(self):
        self.assertEqual(compile_video_evidence(**fixture())["fingerprint"],
                         compile_video_evidence(**fixture())["fingerprint"])

    def test_no_speech_only_physical_verification(self):
        x = fixture()
        x["events"][0]["constraints"] = [
            dict(name="brakes_engaged", state="OBSERVED", witnesses=["speech"])]
        with self.assertRaises(VideoEvidenceError):
            compile_video_evidence(**x)

    def test_no_invented_witness(self):
        x = fixture()
        x["events"][0]["witnesses"] = ["nonexistent"]
        with self.assertRaises(VideoEvidenceError):
            compile_video_evidence(**x)

    def test_no_outside_interval(self):
        x = fixture()
        x["events"][0]["interval"] = {"start_ms": 6000, "end_ms": 7000}
        with self.assertRaises(VideoEvidenceError):
            compile_video_evidence(**x)

    def test_no_duplicate_witness(self):
        x = fixture()
        x["witnesses"].append(dict(x["witnesses"][0]))
        with self.assertRaises(VideoEvidenceError):
            compile_video_evidence(**x)

    def test_no_tampering(self):
        result = compile_video_evidence(**fixture())
        result["events"][0]["constraints"][0]["state"] = "OBSERVED"
        with self.assertRaises(VideoEvidenceError):
            inspect_constraints(result)

    def test_bad_region(self):
        x = fixture()
        x["witnesses"][1]["region"] = [0.9, 0.9, 0.1, 0.1]
        with self.assertRaises(VideoEvidenceError):
            compile_video_evidence(**x)

    def test_no_false_absence_from_missing_visual_data(self):
        x = fixture()
        x["witnesses"] = x["witnesses"][:1]
        x["events"][0]["witnesses"] = ["speech"]
        x["events"][0]["constraints"] = [
            dict(name="brakes_engaged", state="UNKNOWN", witnesses=[])]
        artifact = compile_video_evidence(**x)
        self.assertEqual(inspect_constraints(artifact)[0]["state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
