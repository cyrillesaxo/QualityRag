"""Regressions for finite activation grammar decisions (not semantic admission)."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from activation_constraints import evaluate, validate_grammar, InvalidGrammar


def fixture():
    grammar = {
        "schema": "qualityrag.activation-grammar/v0.1",
        "regimes": {
            "raw": {"preserves": ["symptom", "context", "exact_words"],
                    "exact_fields": ["exact_words"], "payload_bytes": 5000,
                    "activation_ms": 1, "model_bytes": 0},
            "clinical": {"preserves": ["symptom", "context"],
                         "payload_bytes": 100, "activation_ms": 3, "model_bytes": 200},
            "partial": {"preserves": ["symptom"], "unknown_fields": ["context"],
                        "payload_bytes": 30, "activation_ms": 1, "model_bytes": 0}
        },
        "operators": [{"op": "TRANSITION", "from": "raw", "to": "clinical"},
                      {"op": "PRESERVE", "fields": ["symptom", "context"]},
                      {"op": "ACTIVATE", "regime": "clinical", "modules": ["clinical-v1"]},
                      {"op": "VERIFY", "fields": ["symptom"]},
                      {"op": "FALLBACK", "regime": "raw"}]
    }
    contract = {"schema": "qualityrag.activation-contract/v0.1", "task": "triage",
                "source_id": "example-001",
                "required_fields": ["symptom", "context"], "exact_fields": []}
    return grammar, contract, {"symptom": "chest discomfort", "context": "during running"}


class ActivationTest(unittest.TestCase):
    def test_selects_cheapest_declared_feasible_regime(self):
        g, c, obs = fixture()
        r = evaluate(g, c, obs, max_activation_ms=5, max_model_bytes=500,
                     baseline_regime="raw")
        self.assertEqual(r["finite_constraint_result"], "SAT")
        self.assertEqual(r["selected_candidate"], "clinical")
        self.assertEqual(r["qualityrag_admission"], "INCONCLUSIVE")
        self.assertFalse(r["can_generate"])
        self.assertEqual(r["baseline"]["regime"], "raw")
        self.assertEqual(len(r["grammar_sha256"]), 64)

    def test_exact_words_changes_selection(self):
        g, c, obs = fixture()
        c["required_fields"].append("exact_words")
        c["exact_fields"] = ["exact_words"]
        obs["exact_words"] = "My chest hurts when I run"
        r = evaluate(g, c, obs, max_activation_ms=5, max_model_bytes=500)
        self.assertEqual(r["selected_candidate"], "raw")
        clinical = next(x for x in r["regimes"] if x["regime"] == "clinical")
        self.assertIn("EXACT_FIDELITY_NOT_DECLARED", clinical["violations"])

    def test_missing_evidence_unknown_not_sat(self):
        g, c, obs = fixture()
        obs.pop("context")
        r = evaluate(g, c, obs, max_activation_ms=5, max_model_bytes=500)
        self.assertEqual(r["finite_constraint_result"], "UNKNOWN")
        self.assertIsNone(r["selected_candidate"])
        self.assertTrue(all(x["finite_constraint_result"] != "SAT" for x in r["regimes"]))

    def test_resource_budget_enforced(self):
        g, c, obs = fixture()
        r = evaluate(g, c, obs, max_activation_ms=0, max_model_bytes=0)
        self.assertEqual(r["finite_constraint_result"], "UNSAT")
        self.assertIsNone(r["selected_candidate"])

    def test_disallows_unsupported_operations(self):
        g, _, _ = fixture()
        g["operators"].append({"op": "EXEC_PYTHON", "code": "print(1)"})
        with self.assertRaises(InvalidGrammar):
            validate_grammar(g)

    def test_declared_transition_must_exist(self):
        g, _, _ = fixture()
        g["operators"][0]["to"] = "does_not_exist"
        with self.assertRaises(InvalidGrammar):
            validate_grammar(g)

    def test_fidelity_declared_without_preservation_refused(self):
        g, _, _ = fixture()
        g["regimes"]["clinical"]["exact_fields"] = ["exact_words"]
        with self.assertRaises(InvalidGrammar):
            validate_grammar(g)

    def test_unknown_regime_is_not_assumed_absent(self):
        g, c, obs = fixture()
        del g["regimes"]["raw"]
        del g["regimes"]["clinical"]
        g["operators"] = []
        r = evaluate(g, c, obs, max_activation_ms=5, max_model_bytes=500)
        self.assertEqual(r["finite_constraint_result"], "UNKNOWN")
        self.assertEqual(r["regimes"][0]["unresolved"], ["context"])

    def test_duplicate_contract_field_refused(self):
        g, c, obs = fixture()
        c["required_fields"] = ["symptom", "symptom"]
        with self.assertRaises(InvalidGrammar):
            evaluate(g, c, obs, max_activation_ms=5, max_model_bytes=500)

    def test_reproducible_receipts(self):
        g, c, obs = fixture()
        a = evaluate(g, c, obs, max_activation_ms=5, max_model_bytes=500)
        b = evaluate(g, c, obs, max_activation_ms=5, max_model_bytes=500)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
