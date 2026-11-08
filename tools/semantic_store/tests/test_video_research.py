"""Cross-modal research retrieval must keep modality and uncertainty visible."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_catalog import write_evidence, CatalogError
from video_evidence import compile_video_evidence
from video_research import research_video_evidence


def artifact(source_id="course-01", *, speech=True, visual=True):
    witnesses=[]
    if speech:
        witnesses.append({"id":"speech-0","modality":"audio",
            "interval":{"start_ms":1000,"end_ms":3500},
            "text":"Engage the wheelchair brakes before transfer","provider":"test-asr"})
    if visual:
        witnesses.append({"id":"frame-0","modality":"video",
            "interval":{"start_ms":2200,"end_ms":2201},
            "text":"Wheelchair brake lever visible near wheel","provider":"test-vision",
            "frame_sha256":hashlib.sha256(b"frame").hexdigest()})
    return compile_video_evidence(
        source_id=source_id,revision="r1",duration_ms=8000,
        media_sha256=hashlib.sha256(source_id.encode()).hexdigest(),
        witnesses=witnesses,events=[])


class CrossModalResearchTests(unittest.TestCase):
    def test_audio_hit_with_nearby_video_is_not_corrobation(self):
        with tempfile.TemporaryDirectory() as root:
            write_evidence(root,artifact())
            result=research_video_evidence(root,"engage brakes")
            self.assertEqual(result["coverage"],"CROSS_MODAL_CANDIDATES_FOUND_UNVERIFIED")
            first=result["bundles"][0]
            self.assertEqual(first["anchor"]["modality"],"audio")
            self.assertEqual(first["source_time_ref"]["start_ms"],1000)
            self.assertEqual(first["nearby_witnesses"][0]["modality"],"video")
            self.assertEqual(first["speech_visual_agreement"],"NOT_EVALUATED")
            self.assertFalse(first["physical_action_verified"])
            self.assertEqual(result["governance"]["conclusion"],"INCONCLUSIVE")

    def test_visual_intent_requires_visual_lexical_hit(self):
        with tempfile.TemporaryDirectory() as root:
            write_evidence(root,artifact(visual=False))
            result=research_video_evidence(root,"wheelchair",intent="visual")
            self.assertEqual(result["bundles"],[])
            self.assertEqual(result["coverage"],"NO_MATCHES_IN_INDEX_NOT_PROOF_OF_ABSENCE")

    def test_nonoverlapping_video_does_not_count_as_nearby(self):
        with tempfile.TemporaryDirectory() as root:
            a=artifact()
            a["witnesses"][1]["interval"]={"start_ms":7300,"end_ms":7301}
            # Rebuild fingerprint after editing for legitimate fixture.
            from video_evidence import inspect_constraints
            import json
            body=dict(a); body.pop("fingerprint")
            a["fingerprint"]=hashlib.sha256(
                json.dumps(body,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
            ).hexdigest()
            inspect_constraints(a)
            write_evidence(root,a)
            result=research_video_evidence(root,"engage",window_ms=100)
            self.assertEqual(result["bundles"][0]["nearby_witnesses"],[])
            self.assertEqual(result["bundles"][0]["co_observation"],"SINGLE_MODALITY_OR_MISSING")

    def test_bounded_parameters(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(CatalogError):
                research_video_evidence(root,"wheelchair",window_ms=90000)
            with self.assertRaises(CatalogError):
                research_video_evidence(root,"wheelchair",limit=0)


if __name__=="__main__":
    unittest.main()
