"""Behavioral evidence for previously untested story criteria.

These tests exercise outputs and refusal paths; they grant no domain admission.
"""
import copy
from io import BytesIO
import unittest

from tools.activation_runtime.adversaries import challenge, corpus
from tools.activation_runtime.agents import propose
from tools.activation_runtime.common import fingerprint
from tools.activation_runtime.interpreter import execute_plan, exhaustive_equivalence
from tools.activation_runtime.preservation import make_contract
from tools.activation_runtime.search import bounded_search
from test_runtime import policy


class CriterionBehaviorTests(unittest.TestCase):
    def fixture(self):
        raw = b'{"instruction":"must NOT disclose","unit":"mg"}'
        ir = policy()
        contract = make_contract(raw, task="contract", author="author", reviewer="reviewer",
            tenant="tenant", ir=ir, obligations=[{"field":field,"ir_node_id":"custody",
                "mode":"EXACT","tolerance":None,"omission_permitted":False}
                for field in ("instruction", "unit")])
        return raw, ir, contract

    def test_incomplete_execution_returns_unknown_without_output(self):
        raw, ir, contract = self.fixture()
        result = execute_plan(raw, plan=[{"op":"ACTIVATE","runtime":"finite-json/v1"}],
                              contract=contract, ir=ir)
        self.assertEqual(result["finite_constraint_result"], "UNKNOWN")
        self.assertEqual(result["action"], "REFUSE")
        self.assertIsNone(result["output"])
        self.assertFalse(result["can_generate"])

    def test_replay_trace_is_identical_and_inputs_unchanged(self):
        raw, ir, contract = self.fixture()
        plan = [{"op":"TRANSITION","mapping":{"instruction":"i","unit":"u"}},
                {"op":"ACTIVATE","runtime":"finite-json/v1"}, {"op":"VERIFY"}]
        before = copy.deepcopy((plan, ir, contract))
        first = execute_plan(raw, plan=plan, contract=contract, ir=ir)
        second = execute_plan(raw, plan=plan, contract=contract, ir=ir)
        self.assertEqual(first, second)
        self.assertEqual((plan, ir, contract), before)
        self.assertEqual([r["operator"] for r in first["trace"]], ["TRANSITION","ACTIVATE","VERIFY"])
        self.assertEqual(first["finite_constraint_result"], "SAT")

    def test_interpreter_refuses_executable_options_and_excess_steps(self):
        raw, ir, contract = self.fixture()
        for plan in ([{"op":"VERIFY","module":"os"}], [{"op":"IMPORT","module":"os"}],
                     [{"op":"VERIFY"}] * 33):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                execute_plan(raw, plan=plan, contract=contract, ir=ir)

    def test_contract_rejects_tampered_compiler_ir(self):
        raw, ir, _ = self.fixture()
        ir["nodes"][0]["parameters"]["min_independent_sources"] = 99
        with self.assertRaises(ValueError):
            make_contract(raw, task="contract", author="author", reviewer="reviewer", tenant="tenant",
                ir=ir, obligations=[{"field":"unit","ir_node_id":"custody","mode":"EXACT",
                                     "tolerance":None,"omission_permitted":False}])

    def test_graph_sat_remains_scoped_to_declared_vocabulary(self):
        rows = [["a","p","b"]]
        result = exhaustive_equivalence(rows, rows, nodes=["a","b"], relations=["p"])
        self.assertEqual(result["finite_constraint_result"], "SAT")
        self.assertEqual(result["scope"], "DECLARED_FINITE_GRAPH_ONLY")
        self.assertEqual(result["checked_queries"], 4)
        self.assertFalse(result["can_generate"])
        with self.assertRaises(ValueError):
            exhaustive_equivalence(rows, [["a","q","b"]], nodes=["a","b"], relations=["p"])

    def test_blank_pdf_reports_unknown_structure(self):
        from reportlab.pdfgen import canvas
        from tools.activation_runtime.adapters import ingest
        data = BytesIO()
        pdf = canvas.Canvas(data); pdf.showPage(); pdf.save()
        result = ingest(data.getvalue(), format="pdf")
        self.assertEqual(result["coverage"], "UNKNOWN")
        self.assertIn({"page":1,"reason":"NO_TEXT_LAYER_OCR_NOT_EXECUTED"}, result["unsupported"])
        self.assertTrue(result["original_custody_required"])

    def test_fixed_inputs_choose_identical_search_candidate(self):
        source = {"schema":"rct.structured-ast/v1","facts":[
            {"id":"f1","subject":"a","predicate":"p","object":"b","source_ref":"s#1"}]}
        labels = [{"subject":"a","object":"b","positive":True,"source_ref":"l#1"},
                  {"subject":"b","object":"a","positive":False,"source_ref":"l#2"}]
        grammar = {"schema":"rct.typed-operator-grammar/v1.4","predicate_types":{"p":["actor","recipient"]},
                   "operators":["EDGE"],"max_ast_nodes":1,"max_candidates":10}
        first, second = [bounded_search(source,labels,grammar) for _ in range(2)]
        self.assertEqual(first["finite_constraint_result"], "SAT")
        self.assertEqual(first["candidate"], second["candidate"])
        self.assertEqual(first["discarded_candidates"], second["discarded_candidates"])

    def test_guardian_blocks_loss_and_never_certifies_preservation(self):
        for fields, decision in (([], "BLOCK"), (["unit"], "REQUIRES_INDEPENDENT_REVIEW")):
            result = propose("packspec-guardian", parent_grammar={"version":1},
                             task={"required_fields":["unit"],"preserved_fields":fields})
            self.assertEqual(result["status"], "PROPOSAL", result)
            proposal = result["proposal"]
            self.assertEqual(proposal["artifact"]["decision"], decision)
            self.assertEqual(proposal["truth_status"], "UNVERIFIED")
            self.assertFalse(proposal["can_generate"])
            self.assertFalse(proposal["artifact"]["can_generate"])

    def test_proposal_binds_parent_patch_and_rationale(self):
        parent = {"schema":"finite-grammar/v1","max_ast_nodes":1}
        result = propose("grammar-compiler", parent_grammar=parent, task={"max_ast_nodes":3})
        self.assertEqual(result["status"], "PROPOSAL", result)
        proposal = result["proposal"]
        self.assertEqual(proposal["parent_grammar_sha256"], fingerprint(parent))
        self.assertEqual(proposal["artifact"]["patches"], [
            {"op":"replace","path":"/max_ast_nodes","value":1},
            {"op":"replace","path":"/max_ast_nodes","value":3}])
        self.assertTrue(proposal["rationale"].strip())

    def test_unknown_is_missed_counterexample_but_not_false_accept(self):
        cases = corpus()
        bad = [c for c in cases if c["expected"] == "UNSAT"]
        result = challenge(lambda a,b: "UNKNOWN", cases)
        self.assertEqual(result["false_accept_rate"], 0)
        self.assertEqual(result["missed_counterexample_rate"], 1)
        self.assertEqual(result["critical_regressions"], len(bad))
        self.assertEqual(result["promotion"], "BLOCK")
        optimistic = challenge(lambda a,b: "SAT", cases)
        self.assertEqual(optimistic["false_accept_rate"], 1)
        self.assertEqual(optimistic["missed_counterexample_rate"], 1)
