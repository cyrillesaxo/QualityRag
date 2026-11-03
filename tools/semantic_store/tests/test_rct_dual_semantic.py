"""Dual semantic falsification: exact source hashes and refusal dominance.

Synthetic receipts exercise the join. Real signature validation is independently
covered by test_rct_signed_span_review; native APX execution requires original
private APX engine tests.
"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from store import digest
from rct_dual_semantic import combine_semantic_diagnostics


def signed_shape(span_verdict="INCONCLUSIVE"):
    audit={"schema":"rct.source-span-conservation/v2.1",
           "source_sha256":"a"*64, "candidate_sha256":"b"*64,
           "reviewed_inventory_sha256":"c"*64,
           "qualityrag_admission":"INCONCLUSIVE",
           "verdict":span_verdict}
    audit["fingerprint"]=digest(audit)
    joined={"schema":"rct.source-span-joined-candidate/v2.1",
            "source_span_audit":audit,"verdict":span_verdict,
            "qualityrag_admission":"INCONCLUSIVE","can_generate":False}
    joined["fingerprint"]=digest(joined)
    reviewed={"schema":"rct.signed-source-span-inventory/v2.2",
              "joined_candidate_fingerprint":joined["fingerprint"],
              "span_audit_fingerprint":audit["fingerprint"],
              "review_signature":"VERIFIED","verdict":span_verdict,
              "qualityrag_admission":"INCONCLUSIVE","can_generate":False}
    reviewed["fingerprint"]=digest(reviewed)
    return joined,reviewed


def native(verdict="INCONCLUSIVE"):
    return {
        "schema":"qualityrag.native-semantic-transition/v1",
        "original_engine_schema":"apx.semantic-text-transition/v0.1",
        "source_sha256":"a"*64,"candidate_sha256":"b"*64,
        "source_authority":"UNVERIFIED_HEURISTIC",
        "semantic_completeness":"UNKNOWN",
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,"observed_changes":[],
        "verdict":verdict,
    }


class DualSemanticTest(unittest.TestCase):
    def test_both_bounded_checks_still_inconclusive(self):
        j,r=signed_shape()
        result=combine_semantic_diagnostics(j,r,native())
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertEqual(result["native_comparator_status"],"REPORTED_BOUNDED_LEXICAL_CHECK")
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["semantic_completeness"],"UNKNOWN")

    def test_native_detected_drift_refuses(self):
        j,r=signed_shape()
        self.assertEqual(combine_semantic_diagnostics(
            j,r,native("REFUSE"))["verdict"],"REFUSE")

    def test_reviewed_source_span_refusal_dominates_native_pass(self):
        j,r=signed_shape("REFUSE")
        result=combine_semantic_diagnostics(j,r,native())
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")

    def test_missing_original_engine_does_not_silently_pass(self):
        j,r=signed_shape()
        receipt=combine_semantic_diagnostics(j,r,None)
        self.assertEqual(receipt["verdict"],"INCONCLUSIVE")
        self.assertIn("NATIVE_APX_SOURCE_COMPARATOR_NOT_EXECUTED",
                      receipt["blockers"])

    def test_native_cannot_be_reused_for_different_source(self):
        j,r=signed_shape()
        changed=native()
        changed["source_sha256"]="d"*64
        with self.assertRaisesRegex(ValueError,"exact document versions"):
            combine_semantic_diagnostics(j,r,changed)

    def test_missing_review_identity_is_rejected(self):
        j,r=signed_shape()
        r["review_signature"]="UNKNOWN"
        with self.assertRaises(ValueError):
            combine_semantic_diagnostics(j,r,native())

    def test_review_binding_substitution_rejected(self):
        j,r=signed_shape()
        r["joined_candidate_fingerprint"]="0"*64
        r["fingerprint"]=digest({k:v for k,v in r.items() if k!="fingerprint"})
        with self.assertRaises(ValueError):
            combine_semantic_diagnostics(j,r,native())


if __name__=="__main__":
    unittest.main()
