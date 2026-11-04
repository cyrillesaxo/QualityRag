"""Bounded paired experiment tests: no fabricated real-world advantage."""
import io
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from paired_benchmark import compare_directory
from semantic_codex import CodexError


def make_image(color):
    stream=io.BytesIO()
    Image.new("RGB",(40,40),color).save(stream,format="PNG")
    return stream.getvalue()


class FixtureEncoder:
    model_id="DETERMINISTIC_FIXTURE_NOT_REAL_MODEL"
    def image(self,data):
        with Image.open(io.BytesIO(data)) as im:
            red,green,blue=im.convert("RGB").getpixel((1,1))
        return [1.0,0.0] if red>blue else [0.0,1.0]
    def text(self,text):
        return [1.0,0.0] if "presentation" in text else [0.0,1.0]


class PairedComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        # Filename is deliberately unrelated to content to expose the limited
        # lexical baseline, NOT to demonstrate superior real visual reasoning.
        (self.root/"a.png").write_bytes(make_image("blue"))
        (self.root/"b.png").write_bytes(make_image("red"))
        (self.root/"c.png").write_bytes(make_image("blue"))
        self.manifest={
            "schema":"qualityrag.paired-benchmark-input/v0.7",
            "items":[
              {"path":"a.png","relevance":{"q1":"NOT_RELEVANT"}},
              {"path":"b.png","relevance":{"q1":"RELEVANT"}},
              {"path":"c.png","relevance":{"q1":"NOT_RELEVANT"}},
            ],
            "queries":[{"id":"q1","prompt":"person giving a presentation",
                        "lexical_terms":["presentation"]}],
        }
        self.allow=lambda principal,source,revision:principal=="owner" and source.startswith("bench/")

    def tearDown(self):
        self.tmp.cleanup()

    def run_bench(self,manifest=None,**kwargs):
        return compare_directory(self.root,manifest or self.manifest,
               encoder=FixtureEncoder(),principal="owner",
               authorize_source=self.allow,k=1,**kwargs)

    def test_real_pixels_and_same_scope_both_ranking_paths(self):
        report=self.run_bench()
        self.assertEqual(report["file_count"],3)
        self.assertEqual(report["query_count"],1)
        self.assertEqual(report["baseline_metrics"][0]["precision_at_k"],0.0)
        self.assertEqual(report["visual_metrics"][0]["precision_at_k"],1.0)
        self.assertEqual(report["visual_metrics"][0]["recall_at_k"],1.0)
        self.assertEqual(report["total_cost_comparison"],"NOT_ESTABLISHED")
        self.assertFalse(report["timings"]["model_initialization_included"])
        self.assertEqual(report["dataset_label_provenance"],"CALLER_SUPPLIED_UNVERIFIED")
        self.assertEqual(report["identity_recognition"],"NOT_PERFORMED")

    def test_repeat_runs_do_not_claim_real_model_quality(self):
        one,two=self.run_bench(),self.run_bench()
        self.assertEqual(one["dataset_fingerprint"],two["dataset_fingerprint"])
        self.assertEqual(one["visual_metrics"],two["visual_metrics"])
        self.assertEqual(one["generalization"],"UNMEASURED")

    def test_refuse_uncertain_labels_metrics(self):
        manifest={
          **self.manifest,
          "items":[{**x,"relevance":{"q1":"UNCERTAIN"}}
                   if x["path"]=="b.png" else x for x in self.manifest["items"]]
        }
        report=self.run_bench(manifest)
        self.assertIsNone(report["visual_metrics"][0]["recall_at_k"])
        self.assertEqual(report["visual_metrics"][0]["status"],"INCONCLUSIVE_UNCERTAIN_LABELS")

    def test_incomplete_inventory_fail_closed(self):
        incomplete={**self.manifest,"items":self.manifest["items"][:-1]}
        with self.assertRaises(CodexError):
            self.run_bench(incomplete)

    def test_unauthorized_file_blocks_comparison(self):
        with self.assertRaises(CodexError):
            compare_directory(self.root,self.manifest,
              encoder=FixtureEncoder(),principal="owner",
              authorize_source=lambda p,s,r:not s.endswith("b.png"),k=1)

    def test_incomplete_or_duplicate_label_schema_refused(self):
        malformed={**self.manifest,"items":[
          {**self.manifest["items"][0],"relevance":{}},
          *self.manifest["items"][1:]]}
        with self.assertRaises(CodexError):
            self.run_bench(malformed)
        duplicate={**self.manifest,"items":[
          self.manifest["items"][0],
          self.manifest["items"][0],
          self.manifest["items"][2]]}
        with self.assertRaises(CodexError):
            self.run_bench(duplicate)

    def test_no_name_based_biometric_claim(self):
        changed={**self.manifest,"queries":[
            {"id":"q1","prompt":"Cyrille in a photo","lexical_terms":["Cyrille"]}]}
        result=self.run_bench(changed)
        self.assertEqual(result["identity_recognition"],"NOT_PERFORMED")
        self.assertEqual(result["generalization"],"UNMEASURED")

if __name__=="__main__":
    unittest.main()
