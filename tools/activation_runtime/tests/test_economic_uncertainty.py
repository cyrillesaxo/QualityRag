"""Conservative scenario arithmetic, not evidence of actual revenue or savings."""
from fractions import Fraction
import json
import unittest
from tools.activation_runtime.economics import (
    COMPONENTS,COHORTS,SCOPES,lifecycle,lifecycle_interval,catalog_scenarios,
    catalog_uncertainty,research_frontier,
)
from tools.activation_runtime.agents import schedule


def interval(lower,upper=None,evidence="ASSUMED"):
    return {"lower":lower,"upper":lower if upper is None else upper,"evidence":evidence,"unit":"USD"}


def group(**changes):
    result={name:interval(0,evidence="OBSERVED") for name in COMPONENTS}
    result.update(changes)
    return result


def groups():return {scope:group() for scope in SCOPES}
def cohorts(*,views=10,installs=1,updates=0):return {name:{"installs":installs,"views":views,"update_events":updates} for name in COHORTS}


class EconomicUncertaintyTests(unittest.TestCase):
    def test_cli_runs_the_same_scenario_and_rejects_unsupported_options(self):
        import contextlib
        import io
        from pathlib import Path
        import tempfile
        from tools.activation_runtime.cli import main
        specification={"groups":groups(),"catalog_sizes":[1],"cohorts":cohorts()}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"scenario.json";path.write_text(json.dumps(specification))
            out=io.StringIO()
            with contextlib.redirect_stdout(out):main(["economics","--request",str(path)])
            self.assertEqual(json.loads(out.getvalue()),catalog_uncertainty(**specification))
            path.write_text(json.dumps({**specification,"unreviewed":"option"}))
            with self.assertRaises(ValueError):main(["economics","--request",str(path)])

    def test_possible_and_guaranteed_thresholds_differ_under_ranges(self):
        costs=groups();costs["fixed"]=group(compile=interval(10,20))
        costs["baseline_per_view"]=group(bandwidth=interval(2,3))
        costs["candidate_per_view"]=group(decode=interval(1))
        result=catalog_uncertainty(costs,catalog_sizes=[1],cohorts=cohorts())
        self.assertEqual([row["cohort"] for row in result["rows"]],list(COHORTS))
        for row in result["rows"]:
            self.assertEqual(row["earliest_crossover_views"],6)
            self.assertEqual(row["guaranteed_crossover_views"],21)
            self.assertEqual(row["savings_usd"],{"lower":-10,"upper":10})
            self.assertEqual(row["at_declared_views"],"UNCERTAIN")
        later=catalog_uncertainty(costs,catalog_sizes=[1],cohorts=cohorts(views=21))["rows"][0]
        self.assertEqual(later["savings_usd"]["lower"],1)
        self.assertEqual(later["at_declared_views"],"GUARANTEED_SAVINGS_WITHIN_INPUT_BOUNDS")
        self.assertFalse(result["can_promote"])
        self.assertEqual(result["economic_advantage"],"NOT_ESTABLISHED")

    def test_all_workload_scopes_contribute_to_setup_and_total(self):
        costs=groups()
        for scope,component,value in (("fixed","compile",2),("per_title","encode",3),("per_install","model_distribution",5),
                                      ("per_update","update",7),("baseline_per_view","bandwidth",11),("candidate_per_view","decode",2)):
            costs[scope]=group(**{component:interval(value)})
        row=catalog_uncertainty(costs,catalog_sizes=[2],cohorts=cohorts(views=5,installs=3,updates=4))["rows"][0]
        self.assertEqual(row["setup_usd"],{"lower":51,"upper":51})
        self.assertEqual(row["baseline_usd"],{"lower":55,"upper":55})
        self.assertEqual(row["candidate_usd"],{"lower":61,"upper":61})
        self.assertEqual(row["savings_usd"],{"lower":-6,"upper":-6})
        self.assertEqual(row["guaranteed_crossover_views"],6)

    def test_uncertain_marginal_sign_never_claims_guaranteed_crossover(self):
        costs=groups();costs["fixed"]=group(compile=interval(1))
        costs["baseline_per_view"]=group(bandwidth=interval(1,3))
        costs["candidate_per_view"]=group(decode=interval(2))
        row=catalog_uncertainty(costs,catalog_sizes=[1],cohorts=cohorts())["rows"][0]
        self.assertEqual(row["result"],"POSSIBLE_CROSSOVER_ONLY")
        self.assertEqual(row["earliest_crossover_views"],2)
        self.assertIsNone(row["guaranteed_crossover_views"])

    def test_no_crossover_is_retained_when_even_best_marginal_is_nonpositive(self):
        costs=groups();costs["baseline_per_view"]=group(bandwidth=interval(1,2))
        costs["candidate_per_view"]=group(decode=interval(2,3))
        for row in catalog_uncertainty(costs,catalog_sizes=[1],cohorts=cohorts())["rows"]:
            self.assertEqual(row["result"],"NO_CROSSOVER")
            self.assertIsNone(row["earliest_crossover_views"])
            self.assertIsNone(row["guaranteed_crossover_views"])
            self.assertEqual(row["at_declared_views"],"NO_SAVINGS_WITHIN_INPUT_BOUNDS")

    def test_unknown_component_keeps_every_comparison_inconclusive(self):
        costs=groups();costs["per_title"]["verification"]={"lower":None,"upper":None,"unit":"USD","evidence":"UNKNOWN"}
        result=catalog_uncertainty(costs,catalog_sizes=[1],cohorts=cohorts())
        self.assertEqual(result["classification"],"INCONCLUSIVE")
        self.assertEqual(result["unknown_components"],{"per_title":["verification"]})
        for row in result["rows"]:
            self.assertIsNone(row["candidate_usd"])
            self.assertIsNone(row["savings_usd"])
            self.assertEqual(row["result"],"INCONCLUSIVE")

    def test_lifecycle_bounds_preserve_known_subtotal_without_inventing_unknown_cost(self):
        costs=group(compile=interval(2,3),review={"lower":None,"upper":None,"unit":"USD","evidence":"UNKNOWN"})
        result=lifecycle_interval(costs)
        self.assertIsNone(result["total_usd"])
        self.assertEqual(result["known_subtotal_usd"],{"lower":2,"upper":3})
        self.assertEqual(result["unknown_components"],["review"])
        self.assertEqual(result["interpretation"],"DETERMINISTIC_INPUT_BOUNDS_NOT_CONFIDENCE_INTERVALS")

    def test_interval_rounding_is_outward_even_above_exact_float_integer_range(self):
        exact=2**53+1
        result=lifecycle_interval(group(compile=interval(exact)))
        bounds=result["total_usd"]
        self.assertLessEqual(Fraction(str(bounds["lower"])),exact)
        self.assertGreaterEqual(Fraction(str(bounds["upper"])),exact)
        json.dumps(result,allow_nan=False)

    def test_malformed_or_reversed_intervals_are_refused(self):
        bad=[interval(3,2),interval(-1),interval(True),interval(float('nan')),
             interval(10**1000),{"lower":None,"upper":3,"unit":"USD","evidence":"UNKNOWN"},
             {**interval(1),"unit":"EUR"},{**interval(1),"probability":0.95}]
        for value in bad:
            with self.subTest(value_type=type(value["lower"]).__name__):
                with self.assertRaises(ValueError):lifecycle_interval(group(compile=value))

    def test_incomplete_scopes_components_or_workloads_refuse(self):
        costs=groups();del costs["fixed"]["energy"]
        with self.assertRaises(ValueError):catalog_uncertainty(costs,catalog_sizes=[1],cohorts=cohorts())
        costs=groups();del costs["per_update"]
        with self.assertRaises(ValueError):catalog_uncertainty(costs,catalog_sizes=[1],cohorts=cohorts())
        with self.assertRaises(ValueError):catalog_uncertainty(groups(),catalog_sizes=[1,1],cohorts=cohorts())
        for views in (True,-1,1.5,2**63):
            with self.assertRaises(ValueError):catalog_uncertainty(groups(),catalog_sizes=[1],cohorts=cohorts(views=views))

    def test_decimal_boundary_requires_strictly_more_views_than_equality(self):
        rows=catalog_scenarios(model_bytes=0,compile_usd=0.3,encode_usd_per_title=0,
            baseline_usd_per_view=0.1,candidate_usd_per_view=0,model_usd_per_install=0,
            update_usd_per_install=0,verification_usd_per_title=0,catalog_sizes=[1],cohorts=cohorts())
        self.assertTrue(all(row["break_even_views"]==4 for row in rows))
        costs=groups();costs["fixed"]=group(compile=interval(0.3));costs["baseline_per_view"]=group(bandwidth=interval(0.1))
        row=catalog_uncertainty(costs,catalog_sizes=[1],cohorts=cohorts(views=3))["rows"][0]
        self.assertEqual(row["savings_usd"],{"lower":0,"upper":0})
        self.assertEqual(row["earliest_crossover_views"],4)

    def test_exact_lifecycle_sum_and_overflow_refusal(self):
        costs={name:{"value":0,"evidence":"OBSERVED","unit":"USD"} for name in COMPONENTS}
        costs["compile"]["value"]=0.1;costs["encode"]["value"]=0.2
        self.assertEqual(lifecycle(costs)["total_usd"],0.3)
        for row in costs.values():row["value"]=1e308
        with self.assertRaises(ValueError):lifecycle(costs)
        with self.assertRaises(ValueError):lifecycle_interval({name:interval(1e308) for name in COMPONENTS})

    def test_point_scenario_rejects_fractional_bytes_and_finite_input_overflow(self):
        args=dict(model_bytes=1,compile_usd=1e308,encode_usd_per_title=1e308,baseline_usd_per_view=1,
            candidate_usd_per_view=0,model_usd_per_install=0,update_usd_per_install=0,verification_usd_per_title=0,
            catalog_sizes=[2],cohorts=cohorts())
        with self.assertRaises(ValueError):catalog_scenarios(**args)
        args.update(model_bytes=1.5,compile_usd=1,encode_usd_per_title=0)
        with self.assertRaises(ValueError):catalog_scenarios(**args)

    def test_frontier_includes_total_cost_and_excludes_fidelity_or_unknown_energy(self):
        base={"id":"base","bytes":100,"latency_ms":10,"energy_j":2,"total_usd":3,"fidelity_pass":True}
        result=research_frontier([base,{**base,"id":"small","bytes":90,"total_usd":4},
            {**base,"id":"costly","total_usd":5},{**base,"id":"bad","fidelity_pass":False},
            {**base,"id":"unknown","energy_j":None}])
        self.assertEqual(result["frontier"],["base","small"])
        self.assertEqual(result["unqualified"],["bad","unknown"])
        self.assertFalse(result["can_promote"])

    def test_frontier_rejects_duplicate_ids_and_invalid_values_even_in_unqualified_rows(self):
        row={"id":"same","bytes":100,"latency_ms":10,"energy_j":None,"total_usd":3,"fidelity_pass":True}
        with self.assertRaises(ValueError):research_frontier([row,{**row,"fidelity_pass":False}])
        with self.assertRaises(ValueError):research_frontier([{**row,"total_usd":float('nan')}])


class InvestigationBudgetTests(unittest.TestCase):
    def test_decimal_budget_does_not_drop_a_feasible_second_experiment(self):
        result=schedule([{"id":"a","expected_value":1,"cost":0.1},{"id":"b","expected_value":1,"cost":0.2}],budget=0.3)
        self.assertEqual(result["selected"],["a","b"])
        self.assertEqual(result["remaining_budget"],0)

    def test_exact_rank_does_not_turn_huge_ratios_into_an_infinite_tie(self):
        result=schedule([{"id":"a","expected_value":1e308,"cost":1e-307},
                         {"id":"z","expected_value":1e308,"cost":1e-308}],budget=1e-307)
        self.assertEqual(result["selected"],["z"])

    def test_duplicate_and_invalid_experiment_ids_refuse(self):
        row={"id":"a","expected_value":1,"cost":1}
        with self.assertRaises(ValueError):schedule([row,row],budget=10)
        with self.assertRaises(ValueError):schedule([{**row,"id":""}],budget=10)
        with self.assertRaises(ValueError):schedule([row],budget=10**1000)

    def test_fixed_inputs_are_order_invariant_with_explicit_tie_break(self):
        rows=[{"id":"b","expected_value":2,"cost":2},{"id":"a","expected_value":1,"cost":1}]
        self.assertEqual(schedule(rows,budget=2),schedule(list(reversed(rows)),budget=2))
        self.assertEqual(schedule(rows,budget=2)["selected"],["a"])
