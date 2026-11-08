"""Permission checks and public timestamp reference tests; no platform requests."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_catalog import write_evidence, CatalogError
from video_evidence import compile_video_evidence
from video_sources import register_source, source_reference
from video_research import research_video_evidence


def sample():
    return compile_video_evidence(
        source_id="lesson-01", revision="r1",
        media_sha256=hashlib.sha256(b"media").hexdigest(), duration_ms=12000,
        witnesses=[{"id":"visual1","modality":"video",
                    "interval":{"start_ms":5100,"end_ms":5101},
                    "provider":"model","text":"Wheelchair appears in view"}],
        events=[])


class SourceRegistryTests(unittest.TestCase):
    def test_public_timestamp_citation_requires_rights_and_source_match(self):
        with tempfile.TemporaryDirectory() as root:
            a=sample();write_evidence(root,a)
            self.assertEqual(source_reference(root,"lesson-01",5100)["citation_status"],
                             "NO_APPROVED_PUBLIC_REFERENCE")
            with self.assertRaises(CatalogError):
                register_source(root,source_id="lesson-01",revision="r1",
                    media_sha256=a["source"]["media_sha256"],title="Demo",
                    rights="unknown",public_url="https://youtu.be/abc12",
                    allow_public_citation=True)
            register_source(root,source_id="lesson-01",revision="r1",
                media_sha256=a["source"]["media_sha256"],title="Demo",
                rights="owned",public_url="https://www.youtube.com/watch?v=abc12&tracking=foo",
                allow_public_citation=True)
            ref=source_reference(root,"lesson-01",5100)
            self.assertEqual(ref["citation_status"],"TIMESTAMP_URL_CANDIDATE")
            self.assertIn("t=5",ref["url"])
            self.assertNotIn("tracking",ref["url"])
            query=research_video_evidence(root,"wheelchair")
            self.assertEqual(query["bundles"][0]["source_reference"]["url"],ref["url"])

    def test_private_source_is_never_leaked(self):
        with tempfile.TemporaryDirectory() as root:
            a=sample();write_evidence(root,a)
            register_source(root,source_id="lesson-01",revision="r1",
                media_sha256=a["source"]["media_sha256"],title="Private lesson",
                rights="restricted",public_url="https://youtu.be/abc12",
                allow_public_citation=False)
            ref=source_reference(root,"lesson-01",5100)
            self.assertEqual(ref["citation_status"],"PRIVATE_OR_UNLICENSED")
            self.assertNotIn("url",ref)

    def test_url_boundary_and_source_integrity(self):
        with tempfile.TemporaryDirectory() as root:
            a=sample();write_evidence(root,a)
            opts=dict(source_id="lesson-01",revision="r1",
                      media_sha256=a["source"]["media_sha256"],title="Training",
                      rights="owned",allow_public_citation=True)
            for url in ["http://www.youtube.com/watch?v=abc",
                        "https://evil.example.com/x",
                        "https://youtube.com.evil.test/watch?v=x",
                        "https://username:password@youtube.com/watch?v=x"]:
                with self.subTest(url=url),self.assertRaises(CatalogError):
                    register_source(root,public_url=url,**opts)
            with self.assertRaises(CatalogError):
                register_source(root,public_url="https://youtu.be/abc",
                    **{**opts,"media_sha256":"0"*64})

    def test_registration_cannot_silently_change_rights(self):
        with tempfile.TemporaryDirectory() as root:
            a=sample();write_evidence(root,a)
            args=dict(source_id="lesson-01",revision="r1",
                      media_sha256=a["source"]["media_sha256"],title="Training",
                      rights="owned",public_url="https://youtu.be/example",
                      allow_public_citation=True)
            self.assertEqual(register_source(root,**args)["status"],"REGISTERED")
            self.assertEqual(register_source(root,**args)["status"],"ALREADY_REGISTERED")
            with self.assertRaises(CatalogError):
                register_source(root,**{**args,"title":"Changed title"})


if __name__=="__main__":
    unittest.main()
