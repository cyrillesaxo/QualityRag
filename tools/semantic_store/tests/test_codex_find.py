"""Cross-format query acceptance tests with source authorization."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from semantic_codex import compile_source,CodexError
from codex_find import find_text


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.docs=[
            compile_source(b"name,role\nCyrille,architect\n",
                           source_id="people.csv",revision="1",format="csv"),
            compile_source(b'{"note":"Cyrille attended the event"}',
                           source_id="meeting.json",revision="3",format="json"),
            compile_source(b"WEBVTT\n\n00:00:02.000 --> 00:00:04.000\nCyrille presented\n",
                           source_id="event.vtt",revision="1",format="vtt"),
            compile_source(b'{"note":"Cyrille private"}',
                           source_id="restricted.json",revision="1",format="json"),
        ]

    def query(self,docs=None,**kwargs):
        return find_text(self.docs if docs is None else docs,"Cyrille",
                         principal="viewer",
                         authorize_source=lambda p,s,r:p=="viewer" and s!="restricted.json",
                         **kwargs)

    def test_cross_format_search_has_source_anchors(self):
        result=self.query()
        self.assertEqual({h["format"] for h in result["hits"]},{"csv","json","vtt"})
        self.assertEqual(result["searched_authorized_sources"],3)
        self.assertNotIn("private",str(result))
        cue=next(h for h in result["hits"] if h["format"]=="vtt")
        self.assertEqual(cue["anchor"]["start_ms"],2000)
        self.assertEqual(cue["match_type"],"LEXICAL_EXTRACTED_TEXT")
        self.assertEqual(result["visual_identity_recognition"],"NOT_PERFORMED")

    def test_bounded_hits_report_truncation(self):
        r=self.query(max_hits=1)
        self.assertEqual(len(r["hits"]),1)
        self.assertTrue(r["truncated"])

    def test_tamper_rejected_before_search(self):
        docs=self.docs[:1]
        docs[0]["records"][0]["fields"]["name"]["value"]="Other"
        with self.assertRaises(CodexError):
            self.query(docs)

    def test_authorization_required(self):
        with self.assertRaises(PermissionError):
            find_text(self.docs,"Cyrille",principal="viewer",authorize_source=None)

    def test_no_fabricated_matches(self):
        r=find_text(self.docs,"unmentioned",principal="viewer",
                    authorize_source=lambda p,s,r:s!="restricted.json")
        self.assertEqual(r["hits"],[])
        self.assertEqual(r["source_coverage"],"ONLY_SUPPLIED_COMPILED_ARTIFACTS")

    def test_rejects_bad_bounds(self):
        with self.assertRaises(CodexError):
            self.query(max_hits=0)
        with self.assertRaises(CodexError):
            self.query(max_hits=101)


if __name__=="__main__":
    unittest.main()
