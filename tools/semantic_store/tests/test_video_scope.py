"""Remote source access tests: results must be filtered before ranking."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_catalog import write_evidence,search_evidence
from video_research import research_video_evidence
from video_evidence import compile_video_evidence

def sample(id):
    return compile_video_evidence(
        source_id=id,revision="r1",duration_ms=5000,
        media_sha256=hashlib.sha256(id.encode()).hexdigest(),
        witnesses=[{"id":"w1","modality":"audio",
                    "interval":{"start_ms":1000,"end_ms":2000},
                    "text":"wheelchair brakes training",
                    "provider":"synthetic-test"}],events=[])

class ScopeTests(unittest.TestCase):
    def test_excluded_video_never_appears_in_search_or_research(self):
        with tempfile.TemporaryDirectory() as root:
            write_evidence(root,sample("allowed-1"))
            write_evidence(root,sample("private-2"))
            allowed=frozenset({"allowed-1"})
            results=search_evidence(root,"wheelchair",source_ids=allowed)
            self.assertEqual({x["source_id"] for x in results["results"]},allowed)
            research=research_video_evidence(root,"wheelchair",source_ids=allowed)
            self.assertEqual({x["anchor"]["source_id"] for x in research["bundles"]},allowed)
            empty=research_video_evidence(root,"wheelchair",
                                          source_ids=frozenset({"missing"}))
            self.assertEqual(empty["bundles"],[])
            self.assertNotIn("private-2",str(empty))
    def test_invalid_scope_fails(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(Exception,"source filter"):
                search_evidence(root,"wheelchair",source_ids=["allowed-1"])

if __name__=="__main__":
    unittest.main()
