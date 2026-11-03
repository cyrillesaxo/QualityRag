"""Tests for corrected native-run evidence version, not semantic accuracy."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from hashlib import sha256
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_native_compatibility_v2 import MANIFEST, CORPUS, verify, ResearchEvidenceError


class CorrectedEvidenceTests(unittest.TestCase):
    def test_manifest_consistency(self):
        r = verify()
        self.assertFalse(r["scorecard_cross_checked"])
        self.assertEqual(r["production_admission"], "NOT_AUTHORIZED")

    def change_manifest(self, edit):
        m = json.loads(MANIFEST.read_text())
        edit(m)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "m.json"
            f.write_text(json.dumps(m))
            with self.assertRaises(ResearchEvidenceError):
                verify(manifest_path=f)

    def test_commit_substitution(self):
        self.change_manifest(lambda m: m["apx"].update(run_commit="f"*40))

    def test_artifact_digest_substitution(self):
        self.change_manifest(lambda m: m["apx"].update(artifact_sha256="f"*64))

    def test_workflow_substitution(self):
        self.change_manifest(lambda m: m["apx"].update(workflow_run_id=5))

    def test_detection_inflation(self):
        self.change_manifest(lambda m: m["observed"].update(consequential_detected=12))

    def test_semantic_admit_escalation(self):
        self.change_manifest(lambda m: m["assurance"].update(production_admission="AUTHORIZED"))

    def test_bad_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "corpus.json"
            f.write_bytes(CORPUS.read_bytes()+b" ")
            with self.assertRaisesRegex(ResearchEvidenceError, "Corpus byte mismatch"):
                verify(corpus_path=f)

    def score(self):
        cases = json.loads(CORPUS.read_text())["cases"]
        return dict(schema="apx.qualityrag-native-stress-scorecard/v1",
                    source_corpus_sha256="cb01d8f9f0fc9f86e560f9f771cdae1d99be5cf01153c5a7657a69a391392ecd",
                    cases=18,consequential_cases=12,control_cases=6,
                    counts={"consequential_detected":0,"consequential_abstained":12,
                            "control_flagged":0,"control_abstained":6},
                    can_generate=False,compression_authorized=False,
                    semantic_completeness="UNKNOWN",qualityrag_admission="INCONCLUSIVE",
                    case_outcomes=[dict(case_id=c["id"],label=c["label"],
                        source_sha256=sha256(c["source"].encode()).hexdigest(),
                        candidate_sha256=sha256(c["candidate"].encode()).hexdigest(),
                        verdict="INCONCLUSIVE",
                        outcome="consequential_abstained" if c["label"]=="DRIFT" else "control_abstained")
                        for c in cases])

    def check_score(self, s, bad=False):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"score.json"
            f.write_text(json.dumps(s))
            if bad:
                with self.assertRaises(ResearchEvidenceError):
                    verify(scorecard_path=f)
            else:
                self.assertTrue(verify(scorecard_path=f)["scorecard_cross_checked"])

    def test_valid_shape_not_original_execution(self):
        self.check_score(self.score())

    def test_duplicate_case_id(self):
        s=self.score()
        s["case_outcomes"][1]["case_id"]=s["case_outcomes"][0]["case_id"]
        self.check_score(s,True)

    def test_forged_case_hash(self):
        s=self.score()
        s["case_outcomes"][0]["candidate_sha256"]="0"*64
        self.check_score(s,True)

    def test_aggregate_hides_changed_verdict(self):
        s=self.score()
        s["case_outcomes"][0]["verdict"]="REFUSE"
        self.check_score(s,True)

    def test_untrusted_production_claim(self):
        s=self.score()
        s["can_generate"]=True
        self.check_score(s,True)


if __name__=="__main__":
    unittest.main()
