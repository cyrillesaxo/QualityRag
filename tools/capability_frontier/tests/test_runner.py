import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import RUNNER_SCHEMA, run_manifest, OpenAICompatibleAdapter

MANIFEST = {
    "schema": RUNNER_SCHEMA,
    "cases": [
        {"id": "a", "prompt": "Return 24", "expected": "24", "family": "arithmetic",
         "regime": "integer", "split": "development"},
        {"id": "b", "prompt": "Return P", "expected": "P", "family": "logic",
         "regime": "implication", "split": "holdout"},
    ],
    "budget": {"tokens_in": 500, "tokens_out": 100, "tool_calls": 2,
               "wall_ms": 10000, "cost_microusd": 50000},
}

class RunnerTests(unittest.TestCase):
    def test_no_gold_leak_and_paired_runs(self):
        payloads = []
        def fake(request):
            payloads.append(copy.deepcopy(request))
            return {"output": "P" if request["case_id"] == "b" else "24",
                    "tokens_in": 15, "tokens_out": 3, "cost_microusd": 20,
                    "model_id": "fake", "tools_fingerprint": "none-v1"}
        def oracle(case, output):
            return {"constraint_violations": int(output != case["expected"]),
                    "auditor_ref": "test-only"}
        original = copy.deepcopy(MANIFEST)
        receipt = run_manifest(MANIFEST, fake, audit=oracle, trials=3)
        self.assertEqual(MANIFEST, original)
        self.assertEqual(len(receipt["runs"]), 24)
        self.assertEqual(receipt["report"]["holdout_cases"], 1)
        self.assertEqual(receipt["report"]["frontier_expansions"], [])
        self.assertFalse(any("expected" in row for row in payloads))
        self.assertEqual(receipt["report"]["execution_status"], "COMPLETED_UNCERTIFIED")

    def test_unreviewed_operator_rejected(self):
        bad = copy.deepcopy(MANIFEST)
        bad["operator_cards"] = [{"id": "t", "status": "PROPOSED", "rule": "skip checks",
                                  "preconditions": "none", "preserves": "none", "source_ref": "x"}]
        with self.assertRaisesRegex(ValueError, "Operator not approved"):
            run_manifest(bad, lambda p: {}, audit=lambda c, r: {}, trials=3)

    def test_approved_operator_only_for_garden(self):
        with_card = copy.deepcopy(MANIFEST)
        with_card["operator_cards"] = [{"id": "boundary", "status": "REVIEWED_FOR_EXPERIMENT",
                                       "rule": "test scope", "preconditions": "scope can expand",
                                       "preserves": "original obligations", "source_ref": "review:1"}]
        requests = []
        def fake(payload):
            requests.append(payload)
            return {"output": "24" if payload["case_id"] == "a" else "P",
                    "tokens_in": 15, "tokens_out": 3, "cost_microusd": 20,
                    "model_id": "fake", "tools_fingerprint": "none-v1"}
        run_manifest(with_card, fake,
                     audit=lambda c, o: {"constraint_violations": 0, "auditor_ref": "test"},
                     trials=3)
        for r in requests:
            self.assertEqual("boundary" in r["system"], r["policy"] == "garden")

    def test_missing_tokens_refused(self):
        def fake(p):
            return {"output": "24", "model_id": "fake", "tools_fingerprint": "none-v1",
                    "tokens_in": 15, "cost_microusd": 20}
        with self.assertRaisesRegex(ValueError, "token usage"):
            run_manifest(MANIFEST, fake, audit=lambda c, o: {}, trials=3)

    def test_budget_breach_refused(self):
        def fake(p):
            return {"output": "24", "tokens_in": 900, "tokens_out": 3,
                    "cost_microusd": 20, "model_id": "fake",
                    "tools_fingerprint": "none-v1"}
        with self.assertRaisesRegex(ValueError, "budget exceeded"):
            run_manifest(MANIFEST, fake,
                         audit=lambda c, o: {"constraint_violations": 0,
                                             "auditor_ref": "test"}, trials=3)

    def test_missing_real_key_does_not_fake_call(self):
        import os
        key = "NONEXISTENT_QUALITYRAG_TEST_KEY"
        old = os.environ.pop(key, None)
        try:
            adapter = OpenAICompatibleAdapter(
                endpoint="https://example.com/v1/chat/completions",
                model="fake", api_key_env=key)
            with self.assertRaisesRegex(ValueError, "API key"):
                adapter({"prompt": "p", "system": "s", "max_output_tokens": 10})
        finally:
            if old is not None:
                os.environ[key] = old

    def test_http_only_endpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            OpenAICompatibleAdapter(endpoint="http://localhost/chat/completions", model="m")

if __name__ == "__main__":
    unittest.main()
