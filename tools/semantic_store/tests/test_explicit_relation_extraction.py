"""Actual extraction spans, review-gated graph projection and adversarial tests."""
import json
from hashlib import sha256
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from explicit_relation_extraction import extract_declared_relations, project_reviewed_relations
from semantic_codex import CodexError
from store import SemanticStore
from query import query_context


def fixture():
    return [
        {"id":"event","text":"Cyrille reviewed the memo\nRELATE event RELATES_TO decision\n"},
        {"id":"decision","text":"The decision is conditional\nRELATE decision SUPPORTED_BY minutes\n"},
        {"id":"minutes","text":"Minutes are provisional"},
    ]


class ExplicitRelationTests(unittest.TestCase):
    def setUp(self):
        self.sources=fixture()
        self.db=sqlite3.connect(":memory:")
        self.store=SemanticStore(self.db)
        self.store.initialize()
        self.policy=lambda principal,sid,rev:principal=="owner" and sid.startswith("regime/")
        for s in self.sources:
            revision=sha256(json.dumps({"text":s["text"]},sort_keys=True).encode()).hexdigest()
            self.store.add_source("regime/"+s["id"]+".json",revision,revision,
                                  {"source_authenticity":"UNVERIFIED"})
            self.store.add_object("node:"+s["id"],revision,"regime/"+s["id"]+".json",
                                  revision,"BENCHMARK_CANDIDATE",{"id":s["id"]})

    def tearDown(self):
        self.db.close()

    def extract(self):
        return extract_declared_relations(self.sources,principal="owner",
                                          authorize_source=self.policy)

    def review(self,candidates,decisions):
        return [{"candidate_id":c["candidate_id"],"verdict":v}
                for c,v in zip(candidates,decisions)]

    def project(self,extraction,verdicts):
        return project_reviewed_relations(
            self.store,extraction,sources=self.sources,verdicts=verdicts,
            principal="owner",authorize_source=self.policy)

    def test_extracts_exact_source_spans_not_prose_inference(self):
        result=self.extract()
        self.assertEqual(len(result["candidates"]),2)
        self.assertEqual(result["invalid_declarations"],[])
        for c in result["candidates"]:
            source=next(s for s in self.sources if s["id"]==c["evidence_source"])
            anchor=c["anchor"]
            self.assertEqual(source["text"][anchor["start"]:anchor["end"]],
                             c["quoted_evidence"])
            self.assertEqual(anchor["kind"],"text_span")
        self.assertEqual(result["admission"],"INCONCLUSIVE")

    def test_only_caller_supported_edges_enter_graph(self):
        extracted=self.extract()
        result=self.project(extracted,self.review(extracted["candidates"],
                                                    ["SUPPORTED","REJECTED"]))
        self.assertEqual(result["edges_newly_persisted"],1)
        self.assertEqual(result["rejected"],1)
        ctx=query_context(self.store,principal="owner",
                           authorize=lambda p,oid,rev:p=="owner",
                           object_id="node:event",
                           revision=sha256(json.dumps(
                               {"text":self.sources[0]["text"]},sort_keys=True).encode()).hexdigest(),
                           max_hops=1,layers=("KNOWLEDGE",))
        self.assertEqual(len(ctx["edges"]),1)
        self.assertEqual(ctx["edges"][0]["relation"],"RELATES_TO")
        self.assertEqual(ctx["edges"][0]["properties"]["verification"],"NOT_PERFORMED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM semantic_edges").fetchone()[0],1)
        self.assertEqual(result["review_authentication"],"UNVERIFIED")

    def test_ambiguous_review_does_not_create_edges(self):
        extracted=self.extract()
        result=self.project(extracted,self.review(extracted["candidates"],
                                                   ["UNCERTAIN","UNCERTAIN"]))
        self.assertEqual(result["edges_newly_persisted"],0)
        self.assertEqual(result["uncertain"],2)

    def test_idempotent_reviewed_projection(self):
        extracted=self.extract()
        reviews=self.review(extracted["candidates"],["SUPPORTED","SUPPORTED"])
        self.assertEqual(self.project(extracted,reviews)["edges_newly_persisted"],2)
        self.assertEqual(self.project(extracted,reviews)["edges_newly_persisted"],0)

    def test_missing_review_fails_before_writes(self):
        extracted=self.extract()
        with self.assertRaises(CodexError):
            self.project(extracted,self.review(extracted["candidates"],["SUPPORTED"]))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM semantic_edges").fetchone()[0],0)

    def test_tampered_extraction_fails(self):
        extracted=self.extract()
        extracted["candidates"][0]["quoted_evidence"]="invented evidence"
        with self.assertRaises(CodexError):
            self.project(extracted,self.review(extracted["candidates"],
                                                ["SUPPORTED","SUPPORTED"]))

    def test_invalid_declaration_fails_closed(self):
        self.sources[0]["text"]+="RELATE event RELATES_TO ghost\n"
        extracted=self.extract()
        self.assertEqual(len(extracted["invalid_declarations"]),1)
        with self.assertRaises(CodexError):
            self.project(extracted,self.review(extracted["candidates"],
                                                ["SUPPORTED","SUPPORTED"]))

    def test_denied_source_prevents_even_discovery(self):
        with self.assertRaises(PermissionError):
            extract_declared_relations(self.sources,principal="owner",
                authorize_source=lambda p,s,r:not s.endswith("minutes.json"))

    def test_prose_not_misclassified_as_declared_relation(self):
        self.sources[0]["text"]="Cyrille may relate to decision."
        result=self.extract()
        self.assertEqual(len(result["candidates"]),1)
        self.assertEqual(result["candidates"][0]["from"],"decision")

    def test_no_node_registry_bypass(self):
        extraction=self.extract()
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("DELETE FROM semantic_versions")
        self.assertEqual(self.store.db.execute(
            "SELECT COUNT(*) FROM semantic_versions").fetchone()[0],3)


if __name__=="__main__":
    unittest.main()

