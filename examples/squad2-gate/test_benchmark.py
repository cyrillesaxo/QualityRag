import json
import unittest
from pathlib import Path

import run_benchmark as rb

FIXTURE = Path(__file__).with_name("fixture.json")


class BenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.squad, self.digest = rb.load_squad(FIXTURE, download=False)

    def report(self, **kw):
        args = dict(n=10, seed=0, k=1, thresholds=[0.6])
        args.update(kw)
        return {r["labeler"]: r for r in rb.run(self.squad, **args)["rows"]}

    def test_baselines_bracket_the_labeler(self):
        rows = self.report()
        self.assertEqual(rows["no-gate"]["false_admission_rate"], 1.0)
        self.assertEqual(rows["oracle"]["false_admission_rate"], 0.0)
        self.assertEqual(rows["oracle"]["answer_rate"], 1.0)
        self.assertEqual(rows["oracle"]["span_hit_rate"], 1.0)
        self.assertEqual(rows["no-gate"]["positives"] + rows["no-gate"]["negatives"], 4)

    def test_retrieval_selects_matching_paragraph(self):
        q = next(x for x in rb.questions(self.squad) if x["id"] == "q3")
        self.assertEqual(rb.retrieve(q["question"], q["paragraphs"], 1), [1])

    def test_lexical_admits_adversarial_unanswerable(self):
        # q2/q4 are lexically close to their paragraphs; the lexical baseline is expected to be fooled.
        lex = self.report()["lexical@0.6"]
        self.assertGreater(lex["counts"]["neg_impossible_admit"], 0)

    def test_llm_labeler_path_with_stub(self):
        def complete(prompt):
            if "Lena Varga" in prompt and "designed" in prompt.split("Passage:")[0]:
                return '{"status": "SUPPORTS", "quote": "designed by the engineer Lena Varga"}'
            if "abolished in 1988" in prompt and "abolished?" in prompt:
                return '{"status": "SUPPORTS", "quote": "abolished in 1988"}'
            return '{"status": "UNKNOWN", "quote": ""}'
        rows = {r["labeler"]: r for r in rb.run(self.squad, 10, 0, 1, [], llm_complete=complete)["rows"]}
        gated = rows["gate + llm labeler"]
        self.assertEqual(gated["false_admission_rate"], 0.0)
        self.assertEqual(gated["answer_rate"], 1.0)
        self.assertEqual(gated["span_hit_rate"], 1.0)
        self.assertIn("llm-self-abstain (no gate)", rows)  # stub never answers in self-abstain format
        self.assertEqual(rows["llm-self-abstain (no gate)"]["false_admission_rate"], 0.0)

    def test_self_abstain_baseline(self):
        items = rb.sample(self.squad, 10, 0)

        def overconfident(prompt):
            # answers everything, correctly when it can: the failure mode the gate is meant to catch
            if "Who designed" in prompt:
                return '{"answer": "Lena Varga"}'
            if "abolished?" in prompt:
                return '{"answer": "in 1988"}'
            return '{"answer": "1950"}'
        row = rb.self_abstain(items, 1, overconfident)
        self.assertEqual(row["answer_rate"], 1.0)
        self.assertEqual(row["false_admission_rate"], 1.0)
        self.assertEqual(row["answer_match_rate"], 1.0)

        def careful(prompt):
            return '{"answer": "UNANSWERABLE"}' if ("demolished" in prompt or "introduced" in prompt) else '{"answer": "x"}'
        row = rb.self_abstain(items, 1, careful)
        self.assertEqual(row["false_admission_rate"], 0.0)

        def broken(prompt):
            raise RuntimeError("quota")
        self.assertEqual(rb.self_abstain(items, 1, broken)["answer_rate"], 0.0)

    def test_answer_matching(self):
        self.assertTrue(rb.answer_matches("It was Lena Varga.", ["Lena Varga"]))
        self.assertTrue(rb.answer_matches("1988", ["in 1988"]))
        self.assertFalse(rb.answer_matches("", ["1988"]))
        self.assertFalse(rb.answer_matches("1987", ["1988"]))

    def test_cached_completer(self):
        import tempfile
        calls = []
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.jsonl"
            first = rb.CachedCompleter(lambda p: calls.append(p) or f"r:{p}", path, "m")
            self.assertEqual(first("a"), "r:a")
            self.assertEqual(first("a"), "r:a")
            second = rb.CachedCompleter(lambda p: calls.append(p) or "new", path, "m")
            self.assertEqual(second("a"), "r:a")
            other_model = rb.CachedCompleter(lambda p: calls.append(p) or "other", path, "m2")
            self.assertEqual(other_model("a"), "other")
            self.assertEqual(calls, ["a", "a"])
            self.assertEqual((second.hits, second.misses), (1, 0))

            def boom(p):
                raise TimeoutError
            failing = rb.CachedCompleter(boom, path, "m3")
            with self.assertRaises(TimeoutError):
                failing("a")
            self.assertEqual(len(path.read_text().splitlines()), 2)

    def test_render_table(self):
        table = rb.render(rb.run(self.squad, 10, 0, 1, [0.6])["rows"])
        self.assertIn("| no-gate |", table)
        self.assertIn("false_admission_rate", table)

    def test_main_writes_json(self):
        out = Path(self.id().replace(".", "_") + ".json")
        try:
            rb.main(["--data", str(FIXTURE), "--n", "4", "--json", str(out)])
            data = json.loads(out.read_text())
            self.assertEqual(data["dataset"]["sha256"], self.digest)
        finally:
            out.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
