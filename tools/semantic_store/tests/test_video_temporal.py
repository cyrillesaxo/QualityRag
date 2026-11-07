"""Temporal co-observation tests (no models or media required)."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_temporal import group_observations
from video_evidence import VideoEvidenceError


class TimelineTests(unittest.TestCase):
    def test_audio_and_video_coexist_without_verification(self):
        witnesses = [
            {"id":"a", "modality":"audio","interval":{"start_ms":100,"end_ms":500}},
            {"id":"v", "modality":"video","interval":{"start_ms":200,"end_ms":201}},
        ]
        events = group_observations(witnesses, 1000, window_ms=1000)
        self.assertEqual(events[0]["witnesses"], ["a", "v"])
        self.assertEqual(events[0]["constraints"], [])
        self.assertEqual(events[0]["changes"], [])

    def test_long_speech_crosses_windows(self):
        witnesses = [{"id":"a", "modality":"audio",
                      "interval":{"start_ms":100,"end_ms":1900}}]
        events = group_observations(witnesses, 2000, window_ms=1000)
        self.assertEqual(len(events), 2)
        self.assertEqual([e["witnesses"] for e in events], [["a"], ["a"]])

    def test_empty_interval_does_not_infer_absence(self):
        self.assertEqual(group_observations([], 1000, window_ms=100), [])

    def test_bounded_event_budget(self):
        witnesses = [{"id":"a", "modality":"audio",
                      "interval":{"start_ms":0,"end_ms":3000}}]
        with self.assertRaises(VideoEvidenceError):
            group_observations(witnesses, 3000, window_ms=1000, max_events=2)

    def test_reject_invalid_witness_time(self):
        witnesses = [{"id":"a", "modality":"audio",
                      "interval":{"start_ms":100,"end_ms":100}}]
        with self.assertRaises(VideoEvidenceError):
            group_observations(witnesses, 1000)


if __name__ == "__main__":
    unittest.main()
