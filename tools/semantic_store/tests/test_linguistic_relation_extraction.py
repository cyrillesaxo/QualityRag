"""Constrained ordinary-English relation extraction and refusal regression."""
import json
import sqlite3
from hashlib import sha256
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from linguistic_relation_extraction import (
    extract_linguistic_relations, compare_extractors, project_linguistic_reviews)
from semantic_codex import CodexError
from store import SemanticStore

def fixture():
    return [
        {"id":"event","text":
         "event supports decision.\nevent does not support decision.\n"
         "RELATE event RELATES_TO decision\n"},
        {"id":"decision","text":"decision references minutes.\n"},
        {"id":"minutes","text":"The minutes are provisional."},
    ]

class LinguisticTests(unittest.TestCase):
    def setUp(self):
        self.sources=fixture()
        self.auth=lambda p,s,r:p=="owner" and s.startswith("regime/")
        self.db=sqlite3.connect(":memory:")
        self.store=SemanticStore(self.db)
        self.store.initialize()
        for s in self.sources:
            revision=sha256(json.dumps({"text":s["text"]},sort_keys=True).encode()).hexdigest()
            self.store.add_source("regime/"+s["id"]+".json",revision,revision,
                                  {"source_authenticity":"UNVERIFIED"})
            self.store.add_object("node:"+s["id"],revision,
                                  "regime/"+s["id"]+".json",revision,
                                  "BENCHMARK_CANDIDATE",{"id":s["id"]})

    def tearDown(self):
        self.db.close()

    def extract(self):
        return extract_linguistic_relations(self.sources,principal="owner",
                                            authorize_source=self.auth)

    def project(self,result,review):
        return project_linguistic_reviews(
            self.store,result,sources=self.sources,
            verdicts=[{"candidate_id":c["candidate_id"],"verdict":verdict,"review_ms":4.0}
                      for c,verdict in zip(result["candidates"],review)],
            principal="owner",authorize_source=self.auth)

    def test_source_spans_and_polarity_conflicts(self):
        result=self.extract()
        self.assertEqual(len(result["candidates"]),3)
        self.assertEqual(len(result["potential_contradictions"]),1)
        self.assertEqual([x["polarity"] for x in result["candidates"]],
                         ["POSITIVE","NEGATIVE","POSITIVE"])
        for c in result["candidates"]:
            source=next(s for s in self.sources if s["id"]==c["evidence_source"])
            span=c["anchor"]
            self.assertEqual(source["text"][span["start"]:span["end"]],
                             c["quoted_evidence"])
        self.assertEqual(result["semantic_entailment"],"NOT_VERIFIED")

    def test_explicit_vs_linguistic_extractor_compared(self):
        result=compare_extractors(self.sources,principal="owner",
                                  authorize_source=self.auth)
        self.assertEqual(result["explicit_declarations"],1)
        self.assertEqual(result["linguistic_candidates"],3)
        self.assertEqual(result["false_positive_rate"],"UNMEASURED")

    def test_conflict_blocks_even_supported_positive_review(self):
        result=self.extract()
        receipt=self.project(result,["SUPPORTED","SUPPORTED","SUPPORTED"])
        self.assertEqual(receipt["persisted_unverified_positive_edges"],1)
        self.assertEqual(receipt["contradictory_candidate_count"],2)
        self.assertEqual(receipt["review_ms_caller_supplied"],12.0)
        row=self.db.execute("SELECT relation FROM semantic_edges").fetchone()
        self.assertEqual(row,("REFERENCES",))
        self.assertEqual(receipt["admission"],"INCONCLUSIVE")

    def test_rejected_and_uncertain_not_written(self):
        result=self.extract()
        receipt=self.project(result,["REJECTED","UNCERTAIN","REJECTED"])
        self.assertEqual(receipt["persisted_unverified_positive_edges"],0)
        self.assertEqual(receipt["rejected_review_count"],2)

    def test_no_identity_or_relationship_from_unconstrained_prose(self):
        self.sources[0]["text"]="Cyrille discussed a decision. It may be related."
        r=self.extract()
        self.assertEqual(len(r["candidates"]),1) # decision references minutes
        self.assertEqual(r["unresolved_mentions"],[])

    def test_missing_entity_is_unresolved_not_inferred(self):
        self.sources[0]["text"]="event supports ghost."
        r=self.extract()
        self.assertEqual(len(r["unresolved_mentions"]),1)
        self.assertEqual(len(r["candidates"]),1)

    def test_ungrammatical_negation_is_not_admitted(self):
        self.sources[0]["text"]="event does not supports decision."
        r=self.extract()
        self.assertEqual(len(r["unresolved_mentions"]),1)
        self.assertEqual(len(r["candidates"]),1)

    def test_tampering_and_incomplete_review_fail(self):
        result=self.extract()
        result["candidates"][0]["relation"]="INVENTED"
        with self.assertRaises(CodexError):
            self.project(result,["SUPPORTED"]*3)
        result=self.extract()
        with self.assertRaises(CodexError):
            self.project(result,["SUPPORTED"])

    def test_unauthorized_inventory_refused(self):
        with self.assertRaises(PermissionError):
            extract_linguistic_relations(self.sources,principal="owner",
                authorize_source=lambda p,s,r:not s.endswith("minutes.json"))

    def test_projection_idempotent(self):
        r=self.extract()
        review=["SUPPORTED","SUPPORTED","SUPPORTED"]
        self.assertEqual(self.project(r,review)["persisted_unverified_positive_edges"],1)
        self.assertEqual(self.project(r,review)["persisted_unverified_positive_edges"],0)

if __name__=="__main__":
    unittest.main()
