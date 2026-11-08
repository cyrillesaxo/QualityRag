"""No-model tests for allowlist, indexing and citations in video MCP core."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_evidence import compile_video_evidence
from video_catalog import (
    CatalogError, permitted_media, write_evidence, read_evidence,
    search_evidence, analyze_authorized_media
)


def example():
    return compile_video_evidence(
        source_id="training-001",revision="r1",
        media_sha256=hashlib.sha256(b"authorized").hexdigest(),
        duration_ms=10000,
        witnesses=[
            {"id":"audio-0","modality":"audio","interval":{"start_ms":1000,"end_ms":2400},
             "text":"Engage the wheelchair brakes","provider":"test-asr"},
            {"id":"frame-0","modality":"video","interval":{"start_ms":2000,"end_ms":2001},
             "text":"Wheelchair brake lever appears visible","provider":"test-vision",
             "frame_sha256":hashlib.sha256(b"frame").hexdigest()}
        ],
        events=[],model_receipts=[])


class CatalogTests(unittest.TestCase):
    def test_search_returns_modality_and_timestamped_unverified_witnesses(self):
        with tempfile.TemporaryDirectory() as root:
            artifact=example()
            self.assertEqual(write_evidence(root,artifact)["status"],"INDEXED")
            self.assertEqual(write_evidence(root,artifact)["status"],"ALREADY_INDEXED")
            result=search_evidence(root,"wheelchair brakes")
            self.assertEqual(len(result["results"]),2)
            self.assertEqual(result["search_type"],"LEXICAL_BASELINE_NOT_SEMANTIC")
            self.assertEqual(result["results"][0]["modality"],"audio")
            self.assertEqual(result["results"][0]["start_ms"],1000)
            self.assertEqual(result["results"][0]["admission"],"UNVERIFIED_OBSERVATION")
            visual=search_evidence(root,"wheelchair",modality="video")
            self.assertEqual(visual["results"][0]["frame_sha256"],artifact["witnesses"][1]["frame_sha256"])
            self.assertEqual(read_evidence(root,"training-001")["fingerprint"],artifact["fingerprint"])

    def test_unknown_or_modified_artifact_cannot_be_returned(self):
        with tempfile.TemporaryDirectory() as root:
            write_evidence(root,example())
            file=Path(root)/".video-evidence"/"training-001.json"
            file.write_text(file.read_text().replace("Wheelchair brake","Invisible brake"))
            with self.assertRaises(CatalogError):
                read_evidence(root,"training-001")
            self.assertEqual(search_evidence(root,"Invisible")["count"],0)

    def test_absolute_and_parent_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            media=Path(root)/"owned.mp4"
            media.write_bytes(b"not a valid video but path is allowed")
            self.assertEqual(permitted_media(root,"owned.mp4"),media)
            with self.assertRaises(CatalogError):
                permitted_media(root,"/tmp/other.mp4")
            with self.assertRaises((CatalogError,FileNotFoundError)):
                permitted_media(root,"../other.mp4")
            with self.assertRaises(CatalogError):
                analyze_authorized_media(root,"owned.mp4",source_id="id")

    def test_source_identifier_cannot_escape_catalog(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(CatalogError):
                read_evidence(root,"../../secret")


if __name__=="__main__":
    unittest.main()
