"""Guardrails for amortization math: missing data never implies free work."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from economics import evaluate_lifecycle
from semantic_codex import CodexError


def receipt(baseline=10.0,visual=5.0):
    return {
        "schema":"qualityrag.paired-visual-benchmark/v0.7",
        "admission":"INCONCLUSIVE","total_cost_comparison":"NOT_ESTABLISHED",
        "model_id":"test-encoder-not-real-evidence",
        "file_count":3,"query_count":2,
        "baseline_metrics":[{"query_id":"a"},{"query_id":"b"}],
        "visual_metrics":[{"query_id":"a"},{"query_id":"b"}],
        "timings":{"directory_index_ms":20.0,"visual_index_ms":100.0,
                   "method":"WALL_CLOCK_NON_ISOLATED_ONE_RUN",
                   "model_initialization_included":False,
                   "queries":[
                       {"query_id":"a","filename_lexical_ms":baseline,
                        "visual_query_ms":visual},
                       {"query_id":"b","filename_lexical_ms":baseline,
                        "visual_query_ms":visual}]},
    }


def measured_extras():
    return {
        "baseline_update_ms_per_source":2.0,
        "visual_update_ms_per_source":12.0,
        "baseline_storage_bytes":1000,
        "visual_storage_bytes":5000,
        "baseline_verification_ms":1.0,
        "visual_verification_ms":4.0,
        "price_per_cpu_second":0.10,
        "price_per_byte_month":0.000001,
        "retention_months":2.0,
    }


class EconomicsTests(unittest.TestCase):
    def test_missing_values_block_total_claim(self):
        out=evaluate_lifecycle(receipt(),repetitions_per_query=20,changed_sources=1)
        self.assertEqual(out["modeled_repeat_workload"]["total_lifecycle_cost"],"UNKNOWN")
        self.assertIsNone(out["break_even"]["query_executions_required"])
        self.assertEqual(len(out["unknown_costs"]),9)
        self.assertEqual(out["admission"],"INCONCLUSIVE")

    def test_break_even_accounts_for_update_storage_and_verification(self):
        out=evaluate_lifecycle(receipt(),repetitions_per_query=20,changed_sources=1,**measured_extras())
        # Initial overhead 100ms, update premium 10ms, verification premium
        # 3ms = 113ms. Storage premium 4000*2*1e-6=0.008 currency.
        # 5ms/query saved at $0.10/sec -> 0.0005 currency/query.
        # Initial extra 113ms = $0.0113, plus storage $0.008 => 39 queries.
        self.assertEqual(out["break_even"]["query_executions_required"],39)
        self.assertEqual(out["modeled_repeat_workload"]["query_executions"],40)
        total=out["modeled_repeat_workload"]["total_lifecycle_cost"]
        self.assertLess(total["visual_currency"],total["baseline_currency"])
        self.assertEqual(out["semantic_parity"],
                         "NOT_ESTABLISHED_FILENAME_BASELINE_HAS_DIFFERENT_CAPABILITIES")

    def test_no_visual_amortization_when_queries_slower(self):
        out=evaluate_lifecycle(receipt(baseline=1.0,visual=5.0),
                               repetitions_per_query=200,changed_sources=0,**measured_extras())
        self.assertIsNone(out["break_even"]["query_executions_required"])
        self.assertEqual(out["break_even"]["reason"],
                         "VISUAL_QUERY_NOT_CHEAPER_UNDER_MEASURED_TIMINGS")

    def test_negative_nan_infinite_inputs_rejected(self):
        for bad in (-1.0,float("nan"),float("inf"),True):
            with self.subTest(bad=bad),self.assertRaises(CodexError):
                evaluate_lifecycle(receipt(),repetitions_per_query=2,changed_sources=1,
                                   baseline_verification_ms=bad)

    def test_zero_query_workload_is_valid_but_not_observed(self):
        out=evaluate_lifecycle(receipt(),repetitions_per_query=0,changed_sources=0,
                               **measured_extras())
        self.assertEqual(out["modeled_repeat_workload"]["query_executions"],0)
        self.assertEqual(out["input_provenance"],
                         "V07_OBSERVED_WALL_CLOCK_PLUS_CALLER_SUPPLIED_SCENARIO")

    def test_fail_closed_malformed_timing_receipt(self):
        r=receipt()
        r["timings"]["queries"].append(r["timings"]["queries"][0])
        with self.assertRaises(CodexError):
            evaluate_lifecycle(r,repetitions_per_query=1,changed_sources=0)
        r=receipt()
        r["timings"]["model_initialization_included"]=True
        with self.assertRaises(CodexError):
            evaluate_lifecycle(r,repetitions_per_query=1,changed_sources=0)

    def test_storage_requires_real_integer_bytes(self):
        extras=measured_extras()
        extras["baseline_storage_bytes"]=12.4
        with self.assertRaises(CodexError):
            evaluate_lifecycle(receipt(),repetitions_per_query=1,changed_sources=0,**extras)

    def test_rejects_unadmitted_receipt_upgrade(self):
        r=receipt()
        r["admission"]="ADMIT"
        with self.assertRaises(CodexError):
            evaluate_lifecycle(r,repetitions_per_query=10,changed_sources=0)


if __name__=="__main__":
    unittest.main()
