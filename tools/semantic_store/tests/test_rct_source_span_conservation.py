"""Adversarial source-span conservation tests across independent regimes.

These are controlled text fixtures, not source-authenticated documents or
canonical G1–G12 classification. This suite only establishes local invariants.
"""
from hashlib import sha256
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rct_source_span_conservation import audit_source_spans
from store import digest


def span(text, quote):
    p = text.index(quote)
    return {"start":p, "end":p+len(quote), "quote":quote}


def item(identifier, kind, source, candidate, source_quote,
         target_quote=None, *, required=True, value="required", observed="required"):
    return {
        "id":identifier, "kind":kind,"required":required,
        "source":span(source,source_quote),
        "target":span(candidate,target_quote) if target_quote is not None else None,
        "expected_value":value, "observed_value":observed if target_quote is not None else None,
    }


def audit(source, candidate, items):
    return audit_source_spans(
        source, candidate,items,
        source_digest=sha256(source.encode()).hexdigest(),
        candidate_digest=sha256(candidate.encode()).hexdigest(),
        reviewed_inventory_digest=digest(items))


class SourceSpanConservationTests(unittest.TestCase):
    def test_nursing_not_except_reversal_is_refused(self):
        source="Select the action the nurse should NOT perform before confirming patient identity."
        candidate="Select the action the nurse should perform before confirming patient identity."
        records=[item("negation","NEGATION",source,candidate,"NOT","should",
                      value="NEGATED",observed="AFFIRMATIVE")]
        result=audit(source,candidate,records)
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertEqual(result["findings"][0]["status"],"CONTRADICTED")
        self.assertFalse(result["can_generate"])

    def test_hvac_exception_omission_refused(self):
        source="Disconnect power before servicing unless the manufacturer requires a live diagnostic."
        candidate="Disconnect power before servicing."
        records=[item("exception","EXCEPTION",source,candidate,
                      "unless the manufacturer requires a live diagnostic")]
        result=audit(source,candidate,records)
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertEqual(result["findings"][0]["status"],"MISSING_REQUIRED")

    def test_driving_temporal_threshold_change_is_refused(self):
        source="The permit holder must wait at least 12 months before the road test."
        candidate="The permit holder must wait at least 6 months before the road test."
        records=[item("duration","NUMBER",source,candidate,"12 months","6 months",
                      value="12",observed="6")]
        self.assertEqual(audit(source,candidate,records)["verdict"],"REFUSE")

    def test_legal_condition_kept_but_not_proven(self):
        source="Refunds are permitted only if the request is made within 30 days."
        candidate="Refunds are permitted only if the request is made within 30 days."
        records=[item("scope","CONDITION",source,candidate,
                      "only if the request is made within 30 days",
                      "only if the request is made within 30 days",
                      value="CONDITIONAL_30_DAYS",observed="CONDITIONAL_30_DAYS")]
        result=audit(source,candidate,records)
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertEqual(result["semantic_completeness"],"UNKNOWN")
        self.assertFalse(result["findings"][0]["independently_verified"])

    def test_optional_distinction_not_sufficient_for_semantic_admit(self):
        source="A neutral example is included as supporting context."
        candidate="A neutral example."
        records=[item("context","SCOPE",source,candidate,"as supporting context",
                      required=False)]
        result=audit(source,candidate,records)
        self.assertEqual(result["findings"][0]["status"],"DECLARED_OPTIONAL_OMISSION")
        self.assertEqual(result["verdict"],"INCONCLUSIVE")

    def test_unmeasured_observation_abstains(self):
        source="A medication must be given by an authorized nurse."
        candidate="A medication must be given by an authorized nurse."
        records=[item("actor","ACTOR",source,candidate,"authorized nurse",
                      "authorized nurse",value="RN",observed=None)]
        result=audit(source,candidate,records)
        self.assertEqual(result["findings"][0]["status"],"UNMEASURED")
        self.assertEqual(result["verdict"],"INCONCLUSIVE")

    def test_forged_source_quotes_and_offsets_rejected(self):
        source="The technician must check pressure."
        candidate="The technician must check pressure."
        records=[item("actor","ACTOR",source,candidate,"technician","technician")]
        records[0]["source"]["start"]+=1
        with self.assertRaisesRegex(ValueError,"quote mismatch"):
            audit(source,candidate,records)

    def test_stale_source_version_rejected(self):
        source="An exception applies."
        candidate="An exception applies."
        records=[item("exception","EXCEPTION",source,candidate,"exception","exception")]
        with self.assertRaisesRegex(ValueError,"Stale"):
            audit_source_spans(
                source+" Changed",candidate,records,
                source_digest=sha256(source.encode()).hexdigest(),
                candidate_digest=sha256(candidate.encode()).hexdigest(),
                reviewed_inventory_digest=digest(records))

    def test_stale_review_inventory_rejected(self):
        source="Only a licensed electrician may complete the installation."
        candidate=source
        records=[item("actor","ACTOR",source,candidate,
                      "licensed electrician","licensed electrician")]
        old=digest(records)
        records[0]["expected_value"]="different"
        with self.assertRaisesRegex(ValueError,"Stale"):
            audit_source_spans(
                source,candidate,records,
                source_digest=sha256(source.encode()).hexdigest(),
                candidate_digest=sha256(candidate.encode()).hexdigest(),
                reviewed_inventory_digest=old)

    def test_duplicate_obligations_rejected(self):
        source="Check identity twice."
        candidate=source
        records=[item("check","OBLIGATION",source,candidate,"Check identity","Check identity")]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            audit(source,candidate,records*2)


if __name__ == "__main__":
    unittest.main()
