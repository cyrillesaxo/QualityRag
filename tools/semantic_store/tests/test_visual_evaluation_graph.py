"""Finite retrieval metrics and visual candidate WitnessGraph tests."""
from io import BytesIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from directory_codex import index_directory
from visual_semantic import index_visual_semantics, find_visual_scenes
from visual_evaluation import evaluate_visual_results
from visual_graph import project_visual_candidates
from semantic_codex import CodexError
from store import SemanticStore
from query import query_context


def png(color):
    image=Image.new("RGB",(36,36),color)
    out=BytesIO()
    image.save(out,format="PNG")
    return out.getvalue()


class FixtureEncoder:
    model_id="fixture:visual-evaluation:v1"
    def image(self,data):
        with Image.open(BytesIO(data)) as im:
            r,g,b=im.convert("RGB").getpixel((0,0))
        return [1.0,0.0] if r>b else [0.0,1.0]
    def text(self,prompt):
        return [1.0,0.0]


class EvaluationGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/"presentation.png").write_bytes(png("red"))
        (self.root/"park.png").write_bytes(png("blue"))
        (self.root/"private.png").write_bytes(png("red"))
        self.db=sqlite3.connect(":memory:")
        self.store=SemanticStore(self.db)
        self.store.initialize()
        self.encoder=FixtureEncoder()
        index_directory(self.store,self.root,namespace="test",principal="owner",
                        authorize_source=lambda *_:True)
        self.policy=lambda p,s,r:p=="owner" and not s.endswith("private.png")
        index_visual_semantics(self.store,self.root,namespace="test",
                               principal="owner",authorize_source=lambda *_:True,
                               encoder=self.encoder)
        self.result=find_visual_scenes(self.store,"presentation at an event",
                           namespace="test",principal="owner",
                           authorize_source=self.policy,encoder=self.encoder)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def labels(self):
        return [{
            "source_id":h["source_id"],"revision":h["revision"],
            "record_id":h["record_id"],
            "label":"RELEVANT" if h["source_id"].endswith("presentation.png")
                    else "NOT_RELEVANT"}
            for h in self.result["results"]]

    def test_real_finite_benchmark_metrics(self):
        self.assertEqual(len(self.result["results"]),2)
        evaluated=evaluate_visual_results(self.result,labels=self.labels(),k=1)
        self.assertEqual(evaluated["precision_at_k"],1.0)
        self.assertEqual(evaluated["recall_at_k"],1.0)
        self.assertEqual(evaluated["coverage"],"LABELED_AUTHORIZED_FINITE_INDEX_ONLY")
        self.assertEqual(evaluated["real_world_generalization"],"UNMEASURED")
        self.assertFalse(evaluated["can_generate"])

    def test_unknown_labels_never_become_scores(self):
        labels=self.labels()
        labels[0]["label"]="UNCERTAIN"
        evaluated=evaluate_visual_results(self.result,labels=labels,k=1)
        self.assertIsNone(evaluated["precision_at_k"])
        self.assertIsNone(evaluated["recall_at_k"])
        self.assertEqual(evaluated["status"],"INCONCLUSIVE_UNCERTAIN_LABELS")

    def test_benchmark_rejects_incomplete_or_duplicate_labels(self):
        labels=self.labels()
        with self.assertRaises(CodexError):
            evaluate_visual_results(self.result,labels=labels[:-1])
        with self.assertRaises(CodexError):
            evaluate_visual_results(self.result,labels=labels+labels[:1])
        truncated=dict(self.result,truncated=True)
        with self.assertRaises(CodexError):
            evaluate_visual_results(truncated,labels=labels)
        altered=dict(self.result,admission="ADMIT")
        with self.assertRaises(CodexError):
            evaluate_visual_results(altered,labels=labels)

    def test_graph_projection_is_unverified_source_link(self):
        out=project_visual_candidates(self.store,self.result,principal="owner",
                                      authorize_source=self.policy)
        self.assertEqual(out["created"],2)
        candidate=self.db.execute(
            "SELECT object_id,revision,payload_json FROM semantic_versions "
            "WHERE kind='MODEL_RETRIEVAL_CANDIDATE' ORDER BY object_id LIMIT 1").fetchone()
        self.assertIn("INCONCLUSIVE",candidate[2])
        self.assertIn("UNKNOWN",candidate[2])
        ctx=query_context(self.store,principal="owner",
                          authorize=lambda p,oid,rev: p=="owner" and
                              not oid.startswith("test/private.png"),
                          object_id=candidate[0],revision=candidate[1],
                          max_hops=1,layers=("WITNESS",))
        self.assertEqual(len(ctx["edges"]),1)
        self.assertEqual(ctx["edges"][0]["relation"],"DERIVED_FROM_CODEX_RECORD")
        self.assertFalse(ctx["edges"][0]["properties"]["independent"])
        self.assertEqual(ctx["admission"],"INCONCLUSIVE")
        second=project_visual_candidates(self.store,self.result,principal="owner",
                                        authorize_source=self.policy)
        self.assertEqual(second["created"],0)

    def test_restricted_candidate_causes_atomic_failure(self):
        other=find_visual_scenes(self.store,"presentation",
            namespace="test",principal="owner",authorize_source=lambda *_:True,
            encoder=self.encoder)
        with self.assertRaises(PermissionError):
            project_visual_candidates(self.store,other,principal="owner",
                                      authorize_source=self.policy)
        count=self.db.execute("SELECT count(*) FROM semantic_versions "
                              "WHERE kind='MODEL_RETRIEVAL_CANDIDATE'").fetchone()[0]
        self.assertEqual(count,0)

    def test_fabricated_source_ref_does_not_create_graph_node(self):
        bad=dict(self.result,results=[dict(self.result["results"][0],record_id="unknown")])
        with self.assertRaises(CodexError):
            project_visual_candidates(self.store,bad,principal="owner",
                                      authorize_source=self.policy)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM semantic_versions "
            "WHERE kind='MODEL_RETRIEVAL_CANDIDATE'").fetchone()[0],0)

    def test_graph_projection_denies_missing_authorizer(self):
        with self.assertRaises(PermissionError):
            project_visual_candidates(self.store,self.result,principal="owner",
                                      authorize_source=None)

if __name__=="__main__":
    unittest.main()
