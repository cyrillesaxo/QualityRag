"""Adversarial checks for the pinned APX native research compatibility record."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_native_compatibility import (
    MANIFEST, CORPUS, CompatibilityEvidenceError, verify,
)


class NativeCompatibilityEvidenceTests(unittest.TestCase):
    def test_pinned_manifest_is_internally_consistent(self):
        result = verify()
        self.assertEqual(result["production_admission"], "NOT_AUTHORIZED")
        self.assertFalse(result["scorecard_cross_checked"])

    def mutate_manifest(self, change):
        source = json.loads(MANIFEST.read_text(encoding="utf-8"))
        document = deepcopy(source)
        change(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(CompatibilityEvidenceError):
                verify(manifest_path=path)

    def test_rejects_production_admission_laundering(self):
        self.mutate_manifest(
            lambda d: d["assurance"].update(production_admission="AUTHORIZED"))

    def test_rejects_semantic_completeness_laundering(self):
        self.mutate_manifest(
            lambda d: d["assurance"].update(semantic_completeness="COMPLETE"))

    def test_rejects_false_claim_of_real_combined_native_run(self):
        self.mutate_manifest(
            lambda d: d["assurance"].update(combined_native_signed_pipeline_executed=True))

    def test_rejects_moved_native_engine_commit(self):
        self.mutate_manifest(lambda d: d["apx"].update(commit="a" * 40))

    def test_rejects_artifact_substitution(self):
        self.mutate_manifest(lambda d: d["apx"].update(artifact_sha256="b" * 64))

    def test_rejects_versioned_contract_drift(self):
        self.mutate_manifest(
            lambda d: d["qualityrag"].update(governance_schema="v2"))

    def test_rejects_score_inflation(self):
        self.mutate_manifest(
            lambda d: d["observed"].update(consequential_detected=12))

    def test_rejects_corrupted_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            path.write_bytes(CORPUS.read_bytes() + b" ")
            with self.assertRaisesRegex(CompatibilityEvidenceError, "digest mismatch"):
                verify(corpus_path=path)

    def scorecard(self):
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        from hashlib import sha256
        return {
            "schema": m["apx"]["scorecard_schema"],
            "source_corpus_sha256": m["qualityrag"]["corpus_sha256"],
            "counts": {k: v for k, v in m["observed"].items()
                       if k not in ("consequential_cases", "control_cases")},
            "case_outcomes": [
                {"case_id": x["id"], "label": x["label"],
                 "verdict": "INCONCLUSIVE",
                 "outcome": ("consequential_abstained" if x["label"] == "DRIFT" else "control_abstained"),
                 "source_sha256": sha256(x["source"].encode()).hexdigest(),
                 "candidate_sha256": sha256(x["candidate"].encode()).hexdigest()}
                for x in corpus["cases"]
            ],
            "cases": 18,
            "consequential_cases": 12,
            "control_cases": 6,
            "compression_authorized": False,
            "qualityrag_admission": "INCONCLUSIVE",
            "can_generate": False,
            "semantic_completeness": "UNKNOWN",
        }

    def check_score(self, score, *, expected_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scorecard.json"
            path.write_text(json.dumps(score), encoding="utf-8")
            if expected_failure:
                with self.assertRaises(CompatibilityEvidenceError):
                    verify(scorecard_path=path)
            else:
                self.assertTrue(verify(scorecard_path=path)["scorecard_cross_checked"])

    def test_reconciles_expected_scorecard_shape(self):
        # Synthetic fixture tests the verifier, NOT independent APX execution.
        self.check_score(self.scorecard())

    def test_rejects_swapped_case_document_digests(self):
        score = self.scorecard()
        score["case_outcomes"][0]["candidate_sha256"] = "0" * 64
        self.check_score(score, expected_failure=True)

    def test_rejects_false_native_detections(self):
        score = self.scorecard()
        score["counts"]["consequential_detected"] = 12
        self.check_score(score, expected_failure=True)

    def test_rejects_inconsistent_per_case_verdict(self):
        score = self.scorecard()
        score["case_outcomes"][0]["verdict"] = "REFUSE"
        self.check_score(score, expected_failure=True)

    def test_rejects_duplicate_case_id(self):
        score = self.scorecard()
        score["case_outcomes"][1]["case_id"] = score["case_outcomes"][0]["case_id"]
        self.check_score(score, expected_failure=True)

    def test_rejects_native_admission_laundering(self):
        score = self.scorecard()
        score["can_generate"] = True
        self.check_score(score, expected_failure=True)


if __name__ == "__main__":
    unittest.main()
