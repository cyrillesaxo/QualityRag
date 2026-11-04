"""Semantic scene search regression: persisted vectors, ACL, version, model and failures."""
from io import BytesIO
from pathlib import Path
import hashlib
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from directory_codex import index_directory
from visual_semantic import index_visual_semantics, find_visual_scenes, initialize, normalize
from semantic_codex import CodexError
from store import SemanticStore


def picture(color):
    image=Image.new("RGB",(36,30),color)
    out=BytesIO()
    image.save(out,format="PNG")
    return out.getvalue()


class EncoderFixture:
    model_id="test:scene-encoder:v1"
    def image(self,data):
        # This is a deterministic TEST DOUBLE, not a visual perception model.
        with Image.open(BytesIO(data)) as img:
            color=img.convert("RGB").getpixel((0,0))
        return [1.0,0.0] if color[0]>color[2] else [0.0,1.0]
    def text(self,prompt):
        return [1.0,0.0] if "presentation" in prompt else [0.0,1.0]


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/"presentation.png").write_bytes(picture("red"))
        (self.root/"garden.png").write_bytes(picture("blue"))
        (self.root/"private.png").write_bytes(picture("red"))
        self.db=sqlite3.connect(":memory:")
        self.store=SemanticStore(self.db)
        self.store.initialize()
        self.encoder=EncoderFixture()
        self.policy=lambda p,s,r:p=="owner" and not s.endswith("private.png")
        index_directory(self.store,self.root,namespace="local",
                        principal="owner",authorize_source=lambda *_: True)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def build(self):
        return index_visual_semantics(
            self.store,self.root,namespace="local",principal="owner",
            authorize_source=self.policy,encoder=self.encoder)

    def search(self,prompt="a presentation in a room"):
        return find_visual_scenes(self.store,prompt,namespace="local",
            principal="owner",authorize_source=self.policy,encoder=self.encoder)

    def test_real_bytes_encoded_and_ranked_with_source_anchors(self):
        report=self.build()
        self.assertEqual(report["indexed_sources"],2)
        result=self.search()
        self.assertEqual(result["results"][0]["source_id"],"local/presentation.png")
        self.assertEqual(result["results"][0]["anchor"]["kind"],"image_frame")
        self.assertNotIn("private.png",str(result))
        self.assertEqual(result["identity_recognition"],"NOT_PERFORMED")
        self.assertEqual(result["admission"],"INCONCLUSIVE")
        self.assertIn("UNCALIBRATED",result["score_meaning"])

    def test_idempotent_and_immutable(self):
        self.build()
        report=self.build()
        self.assertEqual(report["indexed_sources"],0)
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("DELETE FROM codex_visual_embeddings")

    def test_changed_file_never_reused_as_previous_revision(self):
        self.build()
        (self.root/"presentation.png").write_bytes(picture("green"))
        report=self.build()
        self.assertEqual(report["indexed_sources"],0)
        self.assertGreaterEqual(report["skipped_sources"],1)

    def test_model_switch_prevents_mixed_vector_comparison(self):
        self.build()
        class Other(EncoderFixture):
            model_id="test:scene-encoder:v2"
        result=find_visual_scenes(self.store,"presentation",namespace="local",
             principal="owner",authorize_source=self.policy,encoder=Other())
        self.assertEqual(result["results"],[])
        self.assertEqual(result["evaluated_authorized_frames"],0)

    def test_no_unconfigured_identity_determination(self):
        self.build()
        result=self.search("Cyrille")
        self.assertTrue(all(x["verification"]=="NOT_PERFORMED" for x in result["results"]))
        self.assertEqual(result["identity_recognition"],"NOT_PERFORMED")

    def test_invalid_vectors_refused(self):
        for bad in ([0,0],[float("nan"),1],["bad",1],[1],list(range(2049))):
            with self.subTest(bad=str(bad)[:20]),self.assertRaises(CodexError):
                normalize(bad)

    def test_prompt_and_auth_limits(self):
        self.build()
        with self.assertRaises(CodexError):
            self.search("")
        with self.assertRaises(CodexError):
            find_visual_scenes(self.store,"hello",namespace="../private",
                principal="owner",authorize_source=self.policy,encoder=self.encoder)
        with self.assertRaises(CodexError):
            find_visual_scenes(self.store,"hello",namespace="local",
                principal="owner",authorize_source=self.policy,encoder=self.encoder,max_hits=101)

if __name__=="__main__":
    unittest.main()
