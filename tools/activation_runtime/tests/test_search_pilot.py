import unittest
from tools.activation_runtime.search import bounded_search
from tools.activation_runtime.economics import catalog_scenarios
from tools.activation_runtime.pilot import measure


class SearchPilotTests(unittest.TestCase):
    def test_actual_bounded_rct_search_and_identity_baseline(self):
        source={"schema":"rct.structured-ast/v1","facts":[{"id":"f1","subject":"a","predicate":"p","object":"b","source_ref":"source#1"}]}
        labels=[{"subject":"a","object":"b","positive":True,"source_ref":"label#1"},
                {"subject":"b","object":"a","positive":False,"source_ref":"label#2"}]
        grammar={"schema":"rct.typed-operator-grammar/v1.4","predicate_types":{"p":["actor","recipient"]},"operators":["EDGE"],"max_ast_nodes":1,"max_candidates":10}
        result=bounded_search(source,labels,grammar)
        self.assertEqual(result["finite_constraint_result"],"SAT",result)
        self.assertEqual(result["baseline"]["transformation"],"IDENTITY")
        self.assertEqual(bounded_search(source,labels,grammar,memory_bytes=1)["finite_constraint_result"],"UNKNOWN")

    def test_device_classes_never_fabricated(self):
        result=measure({}, {},device_class="mobile",max_memory_bytes=100,max_latency_ns=100)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["action"],"FALLBACK")

    def test_full_cohort_negative_result_is_retained(self):
        result=catalog_scenarios(model_bytes=100,compile_usd=10,encode_usd_per_title=1,baseline_usd_per_view=1,
            candidate_usd_per_view=2,model_usd_per_install=1,update_usd_per_install=1,verification_usd_per_title=1,
            catalog_sizes=[10],cohorts={k:{"installs":1,"views":10,"update_events":1} for k in ("cold-new","frequent","smart-tv","mobile")})
        self.assertTrue(all(row["result"]=="NO_CROSSOVER" and row["break_even_views"] is None for row in result))
