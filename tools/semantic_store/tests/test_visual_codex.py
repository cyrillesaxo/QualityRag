"""Image pixels and video frame appearance indexing regression tests."""
from io import BytesIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from visual_codex import compile_visual, hamming64
from semantic_codex import CodexError
from store import SemanticStore
from directory_codex import index_directory,find_visual_similar,search_store


def png(variant=0):
    image=Image.new("RGB",(64,64),"white")
    pen=ImageDraw.Draw(image)
    pen.rectangle((5+variant,10,32+variant,37),fill="black")
    pen.ellipse((42,42,55,55),fill="gray")
    output=BytesIO()
    image.save(output,format="PNG")
    return output.getvalue()


class VisualCodexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/"reference.png").write_bytes(png())
        (self.root/"similar.png").write_bytes(png())
        (self.root/"other.png").write_bytes(png(15))
        self.db=sqlite3.connect(":memory:")
        self.store=SemanticStore(self.db)
        self.store.initialize()
        self.access=lambda p,s,r:p=="local-owner" and s!="photos/secret.png"

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def index(self):
        return index_directory(self.store,self.root,namespace="photos",
                               principal="local-owner",authorize_source=self.access)

    def test_image_pixels_not_filename_produce_reference_hash(self):
        a=compile_visual(png(),source_id="photos/a.png",revision="1",format="png")
        b=compile_visual(png(),source_id="photos/b.png",revision="1",format="png")
        self.assertEqual(a["records"][0]["fields"]["visual_hash"],
                         b["records"][0]["fields"]["visual_hash"])
        self.assertEqual(a["records"][0]["anchor"]["kind"],"image_frame")
        self.assertEqual(a["identity_recognition"],"NOT_PERFORMED")
        self.assertEqual(a["extraction_coverage"],"BOUNDED_VISUAL_REFERENCE_ONLY")

    def test_directory_visual_lookup_is_not_identity(self):
        report=self.index()
        self.assertEqual(report["coverage"]["indexed"],3)
        res=find_visual_similar(self.store,reference_source_id="photos/reference.png",
                                namespace="photos",principal="local-owner",
                                authorize_source=self.access,max_distance=0)
        self.assertIn("photos/similar.png",{x["source_id"] for x in res["results"]})
        self.assertTrue(all(x["identity_status"]=="UNKNOWN" for x in res["results"]))
        self.assertEqual(res["identity_recognition"],"NOT_PERFORMED")
        self.assertEqual(res["admission"],"INCONCLUSIVE")
        self.assertEqual(search_store(self.store,"Cyrille",namespace="photos",
                                      principal="local-owner",
                                      authorize_source=self.access)["hits"],[])

    def test_video_frame_sampling_with_supplied_fixture_provider(self):
        def fake_frames(data,*,format):
            self.assertEqual(format,"mp4")
            return [(0,png()),(5000,png(15))]
        result=compile_visual(b"simulated-video",source_id="photos/clip.mp4",
                              revision="1",format="mp4",frame_sampler=fake_frames)
        self.assertEqual(len(result["records"]),2)
        self.assertEqual(result["records"][1]["anchor"]["timestamp_ms"],5000)
        self.assertEqual(result["visual_method"],"64_BIT_DHASH_NOT_IDENTITY_OR_OBJECT_SEMANTICS")

    def test_restricted_files_do_not_leak(self):
        (self.root/"secret.png").write_bytes(png())
        self.index()
        res=find_visual_similar(self.store,reference_source_id="photos/reference.png",
                                namespace="photos",principal="local-owner",
                                authorize_source=self.access,max_distance=0)
        self.assertNotIn("secret.png",str(res))

    def test_missing_or_denied_reference_fails(self):
        self.index()
        for ref in ("photos/missing.png","photos/secret.png","../photos/reference.png"):
            with self.subTest(ref=ref),self.assertRaises(CodexError):
                find_visual_similar(self.store,reference_source_id=ref,
                                    namespace="photos",principal="local-owner",
                                    authorize_source=self.access)

    def test_invalid_image_rejected(self):
        with self.assertRaises(CodexError):
            compile_visual(b"not an image",source_id="photos/blank.png",
                           revision="1",format="png")

    def test_hamming_boundaries(self):
        self.assertEqual(hamming64("0000000000000000","ffffffffffffffff"),64)
        self.assertEqual(hamming64("0000000000000000","0000000000000000"),0)
        with self.assertRaises(CodexError):
            hamming64("bad","ffffffffffffffff")

    def test_visual_bounded_limits(self):
        with self.assertRaises(CodexError):
            compile_visual(b"x"*2_000_001,source_id="a",revision="1",format="jpg")
        with self.assertRaises(CodexError):
            compile_visual(b"video",source_id="a",revision="1",format="mp4",
                           frame_sampler=lambda *_a,**_kw:[(0,png())]*13)

if __name__=="__main__":
    unittest.main()
