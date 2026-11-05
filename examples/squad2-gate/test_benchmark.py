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
        self.assertEqual(rows["llm"]["false_admission_rate"], 0.0)
        self.assertEqual(rows["llm"]["answer_rate"], 1.0)
        self.assertEqual(rows["llm"]["span_hit_rate"], 1.0)

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
