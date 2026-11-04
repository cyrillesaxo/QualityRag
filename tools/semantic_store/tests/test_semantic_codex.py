"""Deterministic cross-format Semantic Codex and loss-boundary tests."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from semantic_codex import compile_source,compare_structural_values,CodexError


class CodexTests(unittest.TestCase):
    def compile(self,body,fmt="json",revision="v1"):
        return compile_source(body.encode("utf-8"),source_id="sample",revision=revision,format=fmt)

    def test_json_preserves_typed_fields_and_source_identity(self):
        r=self.compile('[{"name":"Cyrille","count":2,"ok":true,"none":null}]')
        self.assertEqual(r["records"][0]["anchor"]["pointer"],"/0")
        self.assertEqual(r["records"][0]["fields"]["count"],{"type":"NUMBER","value":2})
        self.assertEqual(r["records"][0]["fields"]["ok"],{"type":"BOOLEAN","value":True})
        self.assertEqual(r["records"][0]["fields"]["none"],{"type":"NULL","value":None})
        self.assertEqual(r["governance"]["admission"],"INCONCLUSIVE")
        self.assertEqual(r["identity_recognition"],"NOT_PERFORMED")

    def test_csv_does_not_hallucinate_numbers_or_identity(self):
        r=self.compile("name,count\nCyrille,2\n","csv")
        self.assertEqual(r["records"][0]["fields"]["count"],{"type":"TEXT","value":"2"})
        self.assertEqual(r["records"][0]["anchor"]["row_number"],2)

    def test_cross_format_normalizes_explicit_text_without_claiming_truth(self):
        a=self.compile('{"name":"Cyrille"}')
        b=self.compile("name\nCyrille\n","csv")
        comparison=compare_structural_values(a,b)
        self.assertTrue(comparison["same_typed_fields_in_order"])
        self.assertEqual(comparison["semantic_equivalence"],"UNKNOWN")

    def test_json_number_vs_csv_text_remain_distinct(self):
        a=self.compile('{"count":5}')
        b=self.compile("count\n5\n","csv")
        self.assertFalse(compare_structural_values(a,b)["same_typed_fields_in_order"])

    def test_vtt_preserves_precise_time_anchor(self):
        vtt="WEBVTT\n\n00:00:02.300 --> 00:00:05.400\nCyrille said hello\n\n00:00:07.000 --> 00:00:08.000\nMusic\n"
        r=self.compile(vtt,"vtt")
        self.assertEqual(r["records"][0]["anchor"],{"kind":"time_range","start_ms":2300,"end_ms":5400})
        self.assertEqual(r["records"][0]["fields"]["text"]["value"],"Cyrille said hello")
        self.assertEqual(len(r["records"]),2)

    def test_modified_artifact_rejected(self):
        a=self.compile('{"name":"Cyrille"}')
        a["records"][0]["fields"]["name"]["value"]="Other"
        with self.assertRaises(CodexError):
            compare_structural_values(a,a)

    def test_incomplete_csv_and_ambiguous_headers_refused(self):
        for raw in ("name,age\nCyrille\n",
                    "name,name\nCyrille,Cyrille\n",
                    "name\nCyrille,extra\n"):
            with self.subTest(raw=raw),self.assertRaises(CodexError):
                self.compile(raw,"csv")

    def test_duplicate_json_keys_refused(self):
        with self.assertRaises(CodexError):
            self.compile('{"name":"Cyrille","name":"Other"}')

    def test_complex_json_must_use_future_explicit_adapter(self):
        with self.assertRaises(CodexError):
            self.compile('{"person":{"name":"Cyrille"}}')

    def test_vtt_refuses_unsupported_annotation_and_inverted_time(self):
        for raw in ("WEBVTT\n\nSTYLE\n::cue {color: red}",
                    "WEBVTT\n\n00:00:05.000 --> 00:00:03.000\nHello",
                    "WEBVTT\n\n00:00:05.000 --> 00:00:05.000\nHello"):
            with self.subTest(raw=raw),self.assertRaises(CodexError):
                self.compile(raw,"vtt")

    def test_requires_original_bytes_for_full_reconstruction(self):
        r=self.compile('{"name":"Cyrille"}')
        self.assertFalse(r["reconstruction"]["exact_source_bytes_recoverable_from_ir"])
        self.assertTrue(r["reconstruction"]["source_bytes_required"])

    def test_rejects_invalid_media_and_oversized_data(self):
        with self.assertRaises(CodexError):
            compile_source(b"\xff",source_id="x",revision="1",format="json")
        with self.assertRaises(CodexError):
            compile_source(b"{}",source_id="x",revision="1",format="pdf")
        with self.assertRaises(CodexError):
            compile_source(b"x"*2_000_001,source_id="x",revision="1",format="json")


if __name__=="__main__":
    unittest.main()
