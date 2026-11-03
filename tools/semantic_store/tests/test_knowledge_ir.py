"""Tests for the source-bound, non-authoritative ConstraintIR bridge."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import digest
from knowledge_ir import compile_constraint_ir, persist_constraint_ir, KnowledgeIRValidationError
from store import SemanticStore
import sqlite3


def fixture():
    source_hash = "a" * 64
    nodes = [{
        "node_id": "require-zero-voltage",
        "kind": "TEMPORAL",
        "status": "DEFERRED",
        "runtime": "NOT_IMPLEMENTED",
        "parameters": {"relation": "BEFORE", "anchor": "circuit-test"},
        "source": {
            "source_sha256": source_hash,
            "candidate_id": "C0001",
            "location": "line:4",
            "quotation": "Verify zero voltage before the circuit test.",
            "quotation_sha256": "b" * 64,
        },
        "review": {
            "approved": True,
            "reviewed_by": "fixture-reviewer",
            "rationale": "Preserve source-derived requirement",
            "authentication": "UNVERIFIED_REVIEWER_LABEL",
        },
    }]
    return {
        "schema": "qualityrag.constraint-ir/v1",
        "source": {"sha256": source_hash},
        "nodes": nodes,
        "summary": {
            "total": 1, "evidence_presence_projections": 0,
            "deferred_semantic_constraints": 1,
            "semantic_constraints_executed": 0,
        },
        "scope": "INSPECTION_DERIVED_CANDIDATES_ONLY",
        "assurance": "NO_AUTOMATIC_SEMANTIC_ENFORCEMENT",
        "ir_sha256": digest({"source_sha256": source_hash, "nodes": nodes}),
    }


class KnowledgeIRTests(unittest.TestCase):
    def test_deferred_obligation_remains_unverified(self):
        compiled = compile_constraint_ir(fixture())
        self.assertEqual(compiled["admission"], "INCONCLUSIVE")
        self.assertEqual(compiled["verification"], "UNKNOWN")
        self.assertEqual(compiled["objects"][0]["execution_posture"], "DEFERRED")
        self.assertEqual(compiled["objects"][0]["constraint_kind"], "TEMPORAL")
        self.assertEqual(compiled["protected_obligations"], ["constraint:require-zero-voltage"])

    def test_reject_tampered_payload_even_when_valid_structure(self):
        data = fixture()
        data["nodes"][0]["parameters"]["relation"] = "AFTER"
        with self.assertRaises(KnowledgeIRValidationError):
            compile_constraint_ir(data)

    def test_reject_unverified_source_provenance(self):
        data = fixture()
        data["nodes"][0]["source"]["source_sha256"] = "c" * 64
        data["ir_sha256"] = digest({"source_sha256": data["source"]["sha256"],
                                    "nodes": data["nodes"]})
        with self.assertRaises(KnowledgeIRValidationError):
            compile_constraint_ir(data)

    def test_reject_promoted_review_authentication(self):
        data = fixture()
        data["nodes"][0]["review"]["authentication"] = "TRUSTED"
        data["ir_sha256"] = digest({"source_sha256": data["source"]["sha256"],
                                    "nodes": data["nodes"]})
        with self.assertRaises(KnowledgeIRValidationError):
            compile_constraint_ir(data)

    def test_reject_inconsistent_deferred_summary(self):
        data = fixture()
        data["summary"]["deferred_semantic_constraints"] = 0
        with self.assertRaises(KnowledgeIRValidationError):
            compile_constraint_ir(data)

    def test_atomic_candidate_persistence_and_duplicate_rejection(self):
        db = sqlite3.connect(":memory:")
        try:
            store = SemanticStore(db)
            store.initialize()
            result = persist_constraint_ir(store, source_id="manual", revision="v1",
                                           ir=fixture())
            self.assertEqual(result["admission"], "INCONCLUSIVE")
            obj = store.object_version("manual:constraint:require-zero-voltage", "v1")
            self.assertEqual(obj["verification"], "UNKNOWN")
            self.assertEqual(obj["source"]["source_sha256"], "a" * 64)
            with self.assertRaises(sqlite3.IntegrityError):
                persist_constraint_ir(store, source_id="manual", revision="v1",
                                      ir=fixture())
            count = db.execute("SELECT COUNT(*) FROM semantic_versions").fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            db.close()

    def test_invalid_ir_is_not_partially_persisted(self):
        db = sqlite3.connect(":memory:")
        try:
            store = SemanticStore(db)
            store.initialize()
            data = fixture()
            data["nodes"][0]["status"] = "ADMITTED"
            data["ir_sha256"] = digest({"source_sha256": data["source"]["sha256"],
                                        "nodes": data["nodes"]})
            with self.assertRaises(KnowledgeIRValidationError):
                persist_constraint_ir(store, source_id="manual", revision="v1",
                                      ir=data)
            count = db.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            db.close()

    def test_evaluable_does_not_equal_executed(self):
        data = fixture()
        data["nodes"][0]["status"] = "EVALUABLE"
        data["nodes"][0]["runtime"] = "BOUNDED_TEMPORAL_V0_1"
        data["ir_sha256"] = digest({"source_sha256": data["source"]["sha256"],
                                    "nodes": data["nodes"]})
        result = compile_constraint_ir(data)
        self.assertEqual(result["objects"][0]["verification"], "UNKNOWN")
        self.assertEqual(result["admission"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
