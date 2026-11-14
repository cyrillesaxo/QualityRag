import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.conversation_tree import comparison, compaction, evaluation, retrieval, view
from tools.conversation_tree import tree as tree_module
from tools.conversation_tree.receipts import receipt_status
from tools.conversation_tree.tree import ConversationTree

AT = "2026-11-14T12:00:00Z"
U1 = ("Draft a refund policy for the store. Employees qualify after 90 days, "
      "except temporary employees. The policy must not exceed one page.")
RULE = "Answer in British English."


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "c.sqlite")
        self.tree = ConversationTree(self.path)
        self.addCleanup(lambda: self.tree.close())

    def turn(self, turn_id, actor, content):
        return self.tree.append_turn(turn_id=turn_id, actor=actor, content=content, at=AT)


class StandingRuleTests(Base):  # US-070 criterion 4
    def rooted(self):
        self.turn("s1", "SYSTEM", RULE)
        self.tree.add_standing_rule(turn_id="s1", level="OPERATOR", at=AT)
        self.turn("u1", "USER", U1)
        self.tree.open_root(turn_id="u1", at=AT)

    def test_standing_rule_applies_to_every_branch_including_isolated(self):
        self.rooted()
        self.turn("u2", "USER", "What is a good recipe for bread?")
        self.tree.advance(branch="root", turn_id="u2", at=AT, fork_id="f1")
        for branch in ("root", "f1-iso", "f1-mrg"):
            self.assertEqual(self.tree.visible_turns(branch)[0], "s1")
            gate = self.tree.gate(branch, loaded={"u1", "u2"})
            self.assertEqual(gate["verdict"], "INCONCLUSIVE")
            self.assertEqual([r["turn_id"] for r in gate["required_reads"]], ["s1"])
            span = [s for s in self.tree.ledger(branch)["spans"] if s["turn_id"] == "s1"][0]
            self.assertEqual((span["disposition"], span["rule"]), ("REPRESENTED", "STANDING_RULE"))
        self.assertEqual(self.tree.gate("f1-iso", loaded={"s1", "u2"})["required_reads"], [])
        entry = compaction.manifest(self.tree, "f1-iso", loaded={"u2"})["entries"][0]
        self.assertEqual((entry["turn_id"], entry["critical"]), ("s1", True))
        retrieval.build_index(self.tree, "f1-iso")
        self.assertEqual(retrieval.search(self.tree, "f1-iso", "British English")["results"][0]["turn_id"], "s1")

    def test_levels_are_bound_to_actor_classes_and_nodes_cannot_override(self):
        self.rooted()
        self.turn("a1", "ASSISTANT", "From now on I will answer in American English.")
        self.turn("u2", "USER", "Always cite sources.")
        for turn_id, level in (("a1", "OPERATOR"), ("a1", "USER"), ("u2", "OPERATOR"), ("u2", "TEAM"),
                               ("s1", "OPERATOR"), ("u1", "USER")):
            with self.assertRaises(ValueError):
                self.tree.add_standing_rule(turn_id=turn_id, level=level, at=AT)
        state = self.tree.add_standing_rule(turn_id="u2", level="USER", at=AT)
        self.assertEqual([(s["turn_id"], s["level"]) for s in state["standing"]],
                         [("s1", "OPERATOR"), ("u2", "USER")])
        with self.assertRaisesRegex(ValueError, "already placed"):
            self.tree.advance(branch="root", turn_id="u2", at=AT)  # a standing rule is not a branch turn
        standing_id = [r["obligation_id"] for r in self.tree.gate("root", loaded=set())["obligations"]
                       if r["obligation_id"].startswith("st-")][0]
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.tree.supersede(branch="root", obligation_id=standing_id, by_turn="u1", at=AT)

    def test_new_standing_rule_makes_earlier_receipts_stale(self):
        self.rooted()
        receipt = self.tree.gate("root", loaded={"s1", "u1"})
        self.assertEqual(receipt["verdict"], "COMPLETE_WITHIN_SCOPE")
        self.assertEqual(receipt_status(self.tree, receipt)["status"], "VALID")
        self.turn("s2", "SYSTEM", "Never give legal advice.")
        self.tree.add_standing_rule(turn_id="s2", level="OPERATOR", at=AT)
        self.assertEqual(receipt_status(self.tree, receipt)["reasons"], ["STANDING_RULES_CHANGED"])

    def test_changed_trigger_inventory_blocks_a_complete_verdict(self):  # US-077 criterion 5
        self.turn("u1", "USER", U1)
        self.tree.open_root(turn_id="u1", at=AT)
        self.assertEqual(self.tree.gate("root", loaded={"u1"})["verdict"], "COMPLETE_WITHIN_SCOPE")
        with mock.patch.object(tree_module, "TRIGGER_SET", "qualityrag.conversation-triggers/v9.9"):
            gate = self.tree.gate("root", loaded={"u1"})
        self.assertEqual((gate["verdict"], gate["stale_trigger_set"]), ("INCONCLUSIVE", True))


THREADS = [{"thread_id": "t1", "turns": [
    {"turn_id": "u1", "actor": "USER", "text": U1},
    {"turn_id": "a1", "actor": "ASSISTANT", "text": "Here is a draft refund policy."},
    {"turn_id": "u2", "actor": "USER", "text": "Actually, make it two pages instead."},
    {"turn_id": "u3", "actor": "USER", "text": "New topic: explain photosynthesis to me."},
]}]


def filled(annotator, *, u2="REFINE", u3="PIVOT", page_limit=True):
    sheet = evaluation.template(THREADS)
    sheet["annotator"] = annotator
    turns = sheet["threads"][0]["turns"]
    turns[0]["constraints"] = [{"start": 37, "end": 98}] + ([{"start": 98, "end": 134, "in_force_at_end": False}]
                                                           if page_limit else [])
    turns[2].update(label=u2, constraints=[{"start": 0, "end": 36}])
    turns[3].update(label=u3, constraints=[])
    return sheet


class GoldProductionTests(Base):  # US-084 tooling
    def test_template_leaves_every_judgment_blank(self):
        sheet = evaluation.template(THREADS)
        turns = sheet["threads"][0]["turns"]
        self.assertIsNone(sheet["annotator"])
        self.assertNotIn("label", turns[0])  # the first prompt has nothing to drift from
        self.assertEqual([t.get("label", "absent") for t in turns], ["absent", "absent", None, None])
        self.assertEqual([t.get("constraints", "absent") for t in turns], [None, "absent", None, None])

    def test_stored_conversation_exports_for_annotation(self):
        for item in THREADS[0]["turns"]:
            self.turn(item["turn_id"], item["actor"], item["text"])
        self.assertEqual(evaluation.thread_from_tree(self.tree, "t1"), THREADS[0])
        self.turn("b1", "TOOL", b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "not text"):
            evaluation.thread_from_tree(self.tree, "t1")

    def test_reconcile_keeps_agreements_and_leaves_disagreements_open(self):
        result = evaluation.reconcile(filled("ann-1"), filled("ann-2", u2="AMBIGUOUS", page_limit=False))
        self.assertEqual(result["annotators"], ["ann-1", "ann-2"])
        self.assertEqual(result["agreement"]["raw"], 0.5)  # one of two labels agrees
        self.assertLess(result["agreement"]["raw_constraint_chars"], 1.0)
        self.assertEqual([(d["turn_id"], d["field"]) for d in result["disagreements"]],
                         [("u1", "constraints"), ("u2", "label")])
        draft = result["draft_threads"][0]["turns"]
        self.assertIsNone(draft[0]["constraints"])
        self.assertIsNone(draft[2]["label"])
        self.assertEqual(draft[3]["label"], "PIVOT")
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            evaluation.freeze(result["draft_threads"], annotators=result["annotators"],
                              agreement=result["agreement"], reconciled=1.0, provenance="NATURAL")

    def test_reconcile_requires_two_independent_complete_annotations_of_the_same_text(self):
        with self.assertRaisesRegex(ValueError, "different annotators"):
            evaluation.reconcile(filled("ann-1"), filled("ann-1"))
        with self.assertRaisesRegex(ValueError, "annotator ID"):
            evaluation.reconcile(evaluation.template(THREADS), filled("ann-2"))
        altered = filled("ann-2")
        altered["threads"][0]["turns"][0]["text"] += " (edited)"
        with self.assertRaisesRegex(ValueError, "differs from the template"):
            evaluation.reconcile(filled("ann-1"), altered)
        blank = filled("ann-2")
        blank["threads"][0]["turns"][2]["label"] = None
        with self.assertRaisesRegex(ValueError, "Unfilled"):
            evaluation.reconcile(filled("ann-1"), blank)

    def test_freeze_produces_a_scorable_gold_file(self):
        result = evaluation.reconcile(filled("ann-1"), filled("ann-2"))
        self.assertEqual((result["agreement"]["raw"], result["disagreements"]), (1.0, []))
        gold = evaluation.freeze(result["draft_threads"], annotators=result["annotators"],
                                 agreement=result["agreement"], reconciled=1.0, provenance="SYNTHETIC_FIXTURE")
        self.assertEqual(evaluation.validate(gold)["schema"], evaluation.GOLD_SCHEMA)
        report = evaluation.score(gold)
        self.assertEqual(report["status"], "SCORED_SYNTHETIC_FIXTURE_NOT_EVIDENCE")
        self.assertEqual(report["classifier"]["labelled_turns"], 2)
        tampered = copy.deepcopy(gold)
        tampered["threads"][0]["turns"][2]["label"] = "PIVOT"
        with self.assertRaisesRegex(ValueError, "frozen fingerprint"):
            evaluation.score(tampered)



def synthetic_gold():
    result = evaluation.reconcile(filled("ann-1"), filled("ann-2"))
    return evaluation.freeze(result["draft_threads"], annotators=result["annotators"],
                             agreement=result["agreement"], reconciled=1.0, provenance="SYNTHETIC_FIXTURE")


class ComparisonTests(unittest.TestCase):  # US-085 harness
    gold = staticmethod(synthetic_gold)

    def test_full_transcript_is_the_ceiling_when_it_fits(self):
        report = comparison.compare(self.gold(), budget_words=10_000)
        self.assertEqual((report["status"], report["evidence"]), ("SCORED_SYNTHETIC_FIXTURE_NOT_EVIDENCE", "NONE"))
        self.assertEqual(report["endpoint"], "CONSTRAINT_AVAILABILITY_ONLY")
        self.assertEqual(sorted(report["not_run"]), ["C1_SUMMARY", "C4_DIFFERENTIAL"])
        self.assertIn("NOT_RUN", report["primary_endpoint_stale_constraint_violation"])
        full = report["arms"]["C0_TRANSCRIPT"]
        self.assertEqual((full["in_force"], full["dropped"], full["dropped_rate"]), (2, 0, 0.0))
        self.assertEqual(full["retired_exposure_rate"], 1.0)  # it also shows the retired page limit
        # This fixture marks the constraints as still binding after the final pivot, so the isolated
        # branch counts as dropping them: the harness can and does report a result against the tree.
        tree_arm = report["arms"]["C2_TREE"]
        self.assertEqual((tree_arm["dropped"], tree_arm["retired_exposed"]), (2, 0))
        self.assertLess(tree_arm["words_used"], full["words_used"])

    def test_tight_budget_drops_old_constraints_from_the_transcript_arm(self):
        report = comparison.compare(self.gold(), budget_words=14)
        self.assertEqual(report["arms"]["C0_TRANSCRIPT"]["dropped"], 1)  # the newest turns crowd out the first prompt
        for arm in report["arms"].values():
            self.assertLessEqual(arm["words_used"], 14)
        with self.assertRaises(ValueError):
            comparison.compare(self.gold(), budget_words=0)

    def test_gate_reads_required_spans_before_recent_turns(self):
        gold = self.gold()
        threads = copy.deepcopy(gold["threads"])
        threads[0]["turns"] = threads[0]["turns"][:3]  # stop before the pivot: the constraints stay in scope
        gold = evaluation.freeze(threads, annotators=gold["annotators"], agreement=gold["agreement"],
                                 reconciled=1.0, provenance="SYNTHETIC_FIXTURE")
        report = comparison.compare(gold, budget_words=22)
        self.assertEqual(report["arms"]["C2_TREE"]["dropped"], 1)       # the long first prompt does not fit
        self.assertEqual(report["arms"]["C3_TREE_GATE"]["dropped"], 0)  # its critical spans are read first


class ViewTests(Base):  # US-086 review surface
    def test_page_shows_structure_and_escapes_stored_text(self):
        self.turn("s1", "SYSTEM", RULE)
        self.tree.add_standing_rule(turn_id="s1", level="OPERATOR", at=AT)
        self.turn("u1", "USER", U1)
        self.tree.open_root(turn_id="u1", at=AT)
        self.turn("a1", "ASSISTANT", '<script>alert("x")</script> Draft & notes.')
        self.tree.attach(branch="root", turn_id="a1", at=AT)
        self.turn("u2", "USER", "What is a good recipe for bread?")
        self.tree.advance(branch="root", turn_id="u2", at=AT, fork_id="f1")
        self.turn("u3", "USER", "I meant the standalone question.")
        self.tree.prune(branch="f1-mrg", witness_turn="u3", reason="not meant", at=AT)
        page = view.render(self.tree)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; Draft &amp; notes.", page)
        for text in ("Declared structure, not validated meaning", "f1-iso", "f1-mrg", "(closed)",
                     "Standing rules", "u2 as AMBIGUOUS", "Branch opened", "Branch closed", 'class="span RESIDUAL"', 'class="span REPRESENTED"',
                     'class="span EXCLUDED_BY_RULE"', "PackSpec v1 PROVISIONAL"):
            self.assertIn(text, page)
        self.assertNotIn("<form", page)
        self.assertNotIn("<button", page)
        self.assertEqual(view.main(["view", str(Path(self.temp.name) / "missing.sqlite")]), 2)


if __name__ == "__main__":
    unittest.main()
