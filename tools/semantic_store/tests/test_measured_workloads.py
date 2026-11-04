"""Measured repeated workload acceptance, update and denial tests."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
import sys

from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from measured_workloads import run_measured_workload
from semantic_codex import CodexError


def png(color):
    output=BytesIO()
    Image.new("RGB",(40,40),color).save(output,"PNG")
    return output.getvalue()


class FixtureEncoder:
    """Known synthetic mapping; never a real visual-understanding model."""
    model_id="FIXTURE_NOT_REAL_VISION_MODEL"
    def image(self,data):
        with Image.open(BytesIO(data)) as im:
            r,g,b=im.convert("RGB").getpixel((5,5))
        return [1.0,0.0] if r>b else [0.0,1.0]
    def text(self,prompt):
        return [1.0,0.0] if "presentation" in prompt else [0.0,1.0]


class WorkloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/"a.png").write_bytes(png("blue"))
        (self.root/"b.png").write_bytes(png("red"))
        (self.root/"c.png").write_bytes(png("blue"))
        self.originals={p.name:p.read_bytes() for p in self.root.iterdir()}
        self.manifest={
            "schema":"qualityrag.paired-benchmark-input/v0.7",
            "items":[
                {"path":"a.png","relevance":{"q1":"NOT_RELEVANT"}},
                {"path":"b.png","relevance":{"q1":"RELEVANT"}},
                {"path":"c.png","relevance":{"q1":"NOT_RELEVANT"}}],
            "queries":[{"id":"q1","prompt":"a presentation",
                        "lexical_terms":["presentation"]}]
        }
        self.policy=lambda p,s,r:p=="owner" and s.startswith("bench/")

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self,**kwargs):
        return run_measured_workload(
            self.root,self.manifest,encoder=FixtureEncoder(),
            principal="owner",authorize_source=self.policy,
            repetitions=3,k=1,**kwargs)

    def test_real_queries_updates_and_measured_storage(self):
        report=self.run_it(update_path="b.png")
        self.assertEqual(len(report["query_samples"]),3)
        self.assertEqual(report["warm_query_latency"]["filename"]["count"],2)
        self.assertEqual(report["warm_query_latency"]["visual"]["count"],2)
        self.assertEqual(report["query_samples"][0]["visual_quality"]["precision_at_k"],1)
        self.assertEqual(report["query_samples"][0]["filename_quality"]["precision_at_k"],0)
        self.assertTrue(report["storage_after_initial_index"]["visual_database_bytes"]>0)
        self.assertTrue(report["storage_after_update"]["visual_database_bytes"]>=
                        report["storage_after_initial_index"]["visual_database_bytes"])
        self.assertEqual(report["source_update"]["changed_source"],"b.png")
        self.assertIn("APPEND_ONLY",report["source_update"]["version_retention"])
        self.assertEqual(report["full_lifecycle_cost"],"NOT_ESTABLISHED")
        self.assertEqual(report["model_initialization"],"EXCLUDED")
        self.assertEqual(report["admission"],"INCONCLUSIVE")
        self.assertFalse(report["can_generate"])
        self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir()},
                         self.originals)

    def test_no_update_only_returns_measured_queries(self):
        report=self.run_it()
        self.assertIsNone(report["source_update"])
        self.assertIsNone(report["storage_after_update"])
        self.assertEqual(report["cold_first_in_process"]["not_a_new_process"],True)

    def test_missing_or_undocumented_source_fails(self):
        (self.root/"extra.png").write_bytes(png("red"))
        with self.assertRaises(CodexError):
            self.run_it()

    def test_unauthorized_source_fails(self):
        with self.assertRaises(CodexError):
            run_measured_workload(
                self.root,self.manifest,encoder=FixtureEncoder(),
                principal="owner",authorize_source=lambda p,s,r: not s.endswith("b.png"),
                repetitions=2,k=1)

    def test_invalid_update_and_repetitions_fail(self):
        with self.assertRaises(CodexError):
            self.run_it(update_path="../b.png")
        with self.assertRaises(CodexError):
            run_measured_workload(self.root,self.manifest,
                encoder=FixtureEncoder(),principal="owner",
                authorize_source=self.policy,repetitions=1,k=1)

    def test_unknown_relevance_remains_inconclusive(self):
        self.manifest["items"][1]["relevance"]["q1"]="UNCERTAIN"
        result=self.run_it()
        self.assertTrue(all(run["visual_quality"]["precision_at_k"] is None
                            for run in result["query_samples"]))

    def test_source_symlink_rejected(self):
        target=self.root/"a.png"
        link=self.root/"link.png"
        try:
            link.symlink_to(target)
        except (OSError,NotImplementedError):
            self.skipTest("No symlink support")
        with self.assertRaises(CodexError):
            self.run_it()


if __name__=="__main__":
    unittest.main()
