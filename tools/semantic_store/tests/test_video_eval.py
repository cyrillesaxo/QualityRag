"""Gold-manifest evaluation checks hashes, rights, and explicitly visual targets."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_catalog import CatalogError,write_evidence
from video_evidence import compile_video_evidence
from video_eval import evaluate_manifest


class RealCorpusEvalTests(unittest.TestCase):
    def fixture(self,root):
        video=Path(root)/"recording.mp4"
        # The synthetic bytes test the validation harness, not media decoding.
        video.write_bytes(b"SYNTHETIC TEST BYTES NOT A REAL VIDEO")
        sha=hashlib.sha256(video.read_bytes()).hexdigest()
        write_evidence(root,compile_video_evidence(
            source_id="test-clip",revision="r1",media_sha256=sha,duration_ms=5000,
            witnesses=[
                {"id":"speech","modality":"audio","provider":"test",
                 "interval":{"start_ms":100,"end_ms":3000},
                 "text":"The presenter discusses training."},
                {"id":"frame","modality":"video","provider":"test",
                 "interval":{"start_ms":1500,"end_ms":1501},
                 "text":"A wheelchair brake lever is visible"},
            ],events=[]))
        return {
            "schema":"qualityrag.video-benchmark-manifest/v1",
            "synthetic_only":False,"reviewer":"Test Fixture Reviewer",
            "rights_confirmed":True,"reviewed_original_video":True,
            "sources":{"test-clip":"recording.mp4"},
            "cases":[{"id":"q1","source_id":"test-clip",
                      "target_witness_id":"frame",
                      "query":"wheelchair brake lever"}],
        }

    def test_only_manifest_is_tested_not_real_footage_accuracy(self):
        with tempfile.TemporaryDirectory() as root:
            manifest=self.fixture(root)
            result=evaluate_manifest(root,manifest)
            self.assertEqual(result["media_hashes_checked"],1)
            self.assertEqual(result["cross_modal_target_hit_at_k"],1.0)
            self.assertEqual(result["speech_only_target_hit_at_k"],0.0)
            self.assertIn("SELF_ATTESTED",result["human_review_authenticity"])
            self.assertEqual(result["evidence_admission"],"RETRIEVAL_EVALUATION_ONLY")

    def test_hash_change_and_missing_rights_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            manifest=self.fixture(root)
            manifest["rights_confirmed"]=False
            with self.assertRaisesRegex(CatalogError,"Rights"):
                evaluate_manifest(root,manifest)
            manifest["rights_confirmed"]=True
            (Path(root)/"recording.mp4").write_bytes(b"tampered media")
            with self.assertRaisesRegex(CatalogError,"digest"):
                evaluate_manifest(root,manifest)

    def test_nonsynthetic_declared_and_visual_gold_required(self):
        with tempfile.TemporaryDirectory() as root:
            manifest=self.fixture(root)
            manifest["synthetic_only"]=True
            with self.assertRaises(CatalogError):
                evaluate_manifest(root,manifest)
            manifest["synthetic_only"]=False
            manifest["cases"][0]["target_witness_id"]="speech"
            with self.assertRaisesRegex(CatalogError,"visual or OCR"):
                evaluate_manifest(root,manifest)


if __name__=="__main__":
    unittest.main()
