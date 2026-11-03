"""Exercise canonical reviewed ConstraintIR gate through the RCT candidate bridge."""
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packspec_compiler"))

from typed_ir import _fingerprint
from rct_lens import compile_lens, persist_lens
from rct_packspec_bridge import bind_candidate, evaluate_bound_lens, guarded_candidate_use
from store import SemanticStore, digest

NOW = "2026-11-03T14:00:00Z"


def ir_fixture(deferred=False):
    source_hash = "a" * 64
    evidence = {
        "node_id": "source-evidence",
        "kind": "EVIDENCE_PRESENCE",
        "status": "PROJECTION_ONLY",
        "runtime": "METADATA_GATE_V0_1",
        "parameters": {"requirement_id": "source-check", "min_independent_sources": 1},
        "source": {"source_sha256": source_hash},
        "review": {"approved": True, "authentication": "UNVERIFIED_REVIEWER_LABEL"},
    }
    nodes = [evidence]
    if deferred:
        nodes.append({
            "node_id": "meaning-sufficiency", "kind": "AUTHORITY",
            "status": "DEFERRED", "runtime": "NOT_IMPLEMENTED",
            "parameters": {"role": "reviewer", "scope": "semantic sufficiency"},
            "source": {"source_sha256": source_hash},
            "review": {"approved": True, "authentication": "UNVERIFIED_REVIEWER_LABEL"},
        })
    result = {
        "schema": "qualityrag.constraint-ir/v1",
        "source": {"sha256": source_hash},
        "nodes": nodes,
        "summary": {
            "total": len(nodes),
            "evidence_presence_projections": 1,
            "deferred_semantic_constraints": len(nodes) - 1,
        },
    }
    result["ir_sha256"] = _fingerprint({
        "source_sha256": source_hash, "nodes": nodes})
    return result


class TestPackSpecBridge(unittest.TestCase):
    def setUp(self):
        self.lens = compile_lens(
            "The heart is located in the thorax.",
            lens_id="anatomy", purpose="identify-heart-region",
            required=("heart-location",))
        self.ir = ir_fixture()
        self.binding = bind_candidate(
            self.lens, self.ir, purpose="identify-heart-region")
        self.witnesses = [{
            "id": "source-one", "requirement_id": "source-check",
            "origin": "unverified-annex", "source_ref": "annex#1",
            "status": "SUPPORTS", "observed_at": NOW,
        }]

    def evaluation(self, **overrides):
        args = dict(lens=self.lens, ir=self.ir, binding=self.binding,
                    witnesses=self.witnesses, observations={}, as_of=NOW)
        args.update(overrides)
        return evaluate_bound_lens(**args)

    def test_canonical_gate_checks_pass_but_lens_stays_inconclusive(self):
        outcome = self.evaluation()
        self.assertEqual(outcome["canonical_checks_verdict"], "ADMIT")
        self.assertEqual(outcome["canonical_gate"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(outcome["verdict"], "INCONCLUSIVE")
        self.assertFalse(outcome["can_generate"])
        self.assertEqual(outcome["canonical_gate"]["coverage"]["evidence_nodes"], 1)

    def test_missing_evidence_is_not_admitted(self):
        outcome = self.evaluation(witnesses=[])
        self.assertEqual(outcome["canonical_gate"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(outcome["verdict"], "INCONCLUSIVE")

    def test_explicit_contradiction_refuses(self):
        conflicting = [dict(self.witnesses[0], status="CONTRADICTS")]
        outcome = self.evaluation(witnesses=conflicting)
        self.assertEqual(outcome["verdict"], "REFUSE")
        self.assertFalse(outcome["can_generate"])

    def test_deferred_semantic_node_never_silently_dropped(self):
        ir = ir_fixture(deferred=True)
        binding = bind_candidate(self.lens, ir, purpose=self.lens["purpose"])
        result = self.evaluation(ir=ir, binding=binding)
        self.assertEqual(result["canonical_gate"]["coverage"]["semantic_nodes"], 1)
        self.assertEqual(result["canonical_gate"]["semantics"]["verdict"], "INCONCLUSIVE")

    def test_omission_not_mistaken_for_authorized_safety(self):
        modified = dict(self.lens)
        modified["omitted_fact_ids"] = ["unverified-omission"]
        modified.pop("fingerprint")
        modified["fingerprint"] = digest(modified)
        binding = bind_candidate(modified, self.ir, purpose=modified["purpose"])
        result = self.evaluation(lens=modified, binding=binding)
        self.assertIn("OMISSION_AUTHORIZATION_NOT_ESTABLISHED", result["blockers"])
        self.assertEqual(result["verdict"], "INCONCLUSIVE")

    def test_changed_ir_binding_rejected(self):
        changed = ir_fixture(deferred=True)
        with self.assertRaises(ValueError):
            self.evaluation(ir=changed)

    def test_tampered_lens_rejected(self):
        changed = dict(self.lens, purpose="different-purpose")
        with self.assertRaises(ValueError):
            self.evaluation(lens=changed)

    def test_generator_cannot_fire_even_when_checks_pass(self):
        calls = []
        result = guarded_candidate_use(
            self.lens, self.ir, self.binding, self.witnesses, {}, NOW,
            generator=lambda: calls.append("unsafe"))
        self.assertFalse(result["generated"])
        self.assertIsNone(result["answer"])
        self.assertEqual(calls, [])

    def test_store_and_gate_receipts_remain_separate(self):
        db = sqlite3.connect(":memory:")
        store = SemanticStore(db)
        store.initialize()
        receipt = persist_lens(
            store, lens=self.lens, source_id="anatomy-source",
            revision="v1", packspec_digest=self.ir["ir_sha256"])
        decision = self.evaluation()
        self.assertEqual(receipt["admission"], "INCONCLUSIVE")
        self.assertEqual(decision["verdict"], "INCONCLUSIVE")
        self.assertEqual(
            db.execute("SELECT verdict FROM admission_receipts").fetchone()[0],
            "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
