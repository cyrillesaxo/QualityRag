import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frontier import evaluate, assess_operator

BUDGET = {"tokens_in": 500, "tokens_out": 500, "tool_calls": 10,
          "wall_ms": 1000, "cost_microusd": 1000}
CASES = [
    {"id": "a", "family": "arithmetic", "regime": "rational", "split": "holdout", "expected": 24},
    {"id": "b", "family": "logic", "regime": "conditional", "split": "holdout", "expected": "P and not Q"},
    {"id": "c", "family": "spatial", "regime": "nine-dot", "split": "holdout", "expected": 9},
    {"id": "d", "family": "graph", "regime": "river", "split": "holdout", "expected": 7},
]

def fixture():
    runs = []
    for case in CASES:
        for trial in (1, 2, 3):
            for policy in ("baseline", "tools", "grammar", "garden"):
                runs.append({
                    "case_id": case["id"], "trial": trial, "policy": policy,
                    "model_id": "test-model", "tools_fingerprint": "equal-tools",
                    "output": case["expected"] if policy == "garden" else "wrong",
                    "tokens_in": 20, "tokens_out": 10, "tool_calls": 2,
                    "wall_ms": 50, "cost_microusd": 25,
                    "constraint_violations": 0, "auditor_ref": "fixture-only",
                })
    return runs

class FrontierTests(unittest.TestCase):
    def test_paired_frontier(self):
        report = evaluate(CASES, fixture(), budget=BUDGET)
        self.assertEqual(len(report["frontier_expansions"]), 4)
        self.assertEqual(report["regressions"], [])

    def test_missing_policy_refused(self):
        with self.assertRaisesRegex(ValueError, "Unpaired"):
            evaluate(CASES, fixture()[:-1], budget=BUDGET)

    def test_budget_refused(self):
        rows = fixture()
        rows[0]["tokens_out"] = 999
        with self.assertRaisesRegex(ValueError, "Budget exceeded"):
            evaluate(CASES, rows, budget=BUDGET)

    def test_mismatched_models_refused(self):
        rows = fixture()
        rows[0]["model_id"] = "different-model"
        with self.assertRaisesRegex(ValueError, "Model/tool"):
            evaluate(CASES, rows, budget=BUDGET)

    def test_constraint_violations_cancel_correct_answers(self):
        rows = fixture()
        for row in rows:
            if row["policy"] == "garden" and row["case_id"] == "a":
                row["constraint_violations"] = 1
        self.assertEqual(len(evaluate(CASES, rows, budget=BUDGET)["frontier_expansions"]), 3)

    def test_no_automatic_operator_promotion(self):
        report = evaluate(CASES, fixture(), budget=BUDGET)
        proposal = {"id": "expand-domain", "grammar_version": "v0.1",
                    "function": "solve", "source_regime": "r0", "target_regime": "r1",
                    "preserved_constraints": ["correctness"], "counterexamples": [],
                    "pack_sha256": "sha-of-reviewed-pack"}
        verdict = assess_operator(proposal, report, independently_reviewed=True)
        self.assertFalse(verdict["promotion_authorized"])
        self.assertEqual(verdict["status"], "CANDIDATE")
        self.assertIn("CANONICAL_APX_ADMISSION_REQUIRED", verdict["reasons"])

    def test_no_cross_family_transfer_prevents_claim(self):
        report = evaluate(CASES, fixture(), budget=BUDGET)
        report["frontier_expansions"] = []
        proposal = {"id": "x", "grammar_version": "v1", "function": "solve",
                    "source_regime": "a", "target_regime": "b",
                    "preserved_constraints": ["p"], "counterexamples": [],
                    "pack_sha256": "fingerprint"}
        verdict = assess_operator(proposal, report)
        self.assertIn("NO_CROSS_FAMILY_TRANSFER", verdict["reasons"])

if __name__ == "__main__":
    unittest.main()
