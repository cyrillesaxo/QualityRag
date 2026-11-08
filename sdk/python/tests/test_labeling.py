import unittest
from types import SimpleNamespace

from qualityrag.labeling import (LexicalLabeler, LLMLabeler, Requirement, anthropic_completer,
                                 assess, label_evidence)

PACK = {"id": "p", "version": "1", "requirements": [{"id": "r1"}, {"id": "r2"}]}
AS_OF = "2026-11-02T10:05:00Z"


def passage(pid, text, origin=None):
    return {"id": pid, "text": text, "origin": origin or pid, "source_ref": f"doc#{pid}"}


class LexicalLabelerTest(unittest.TestCase):
    def setUp(self):
        self.lab = LexicalLabeler(0.6)
        self.req = Requirement("r1", "Compliance sign-off is required before restoring the gateway.")

    def test_supports_with_span(self):
        text = "Intro line. Restoring the gateway requires compliance sign-off first. Unrelated."
        lab = self.lab.label(self.req, text)
        self.assertEqual(lab.status, "SUPPORTS")
        self.assertEqual(text[lab.span[0]:lab.span[1]], lab.quote)
        self.assertIn("compliance sign-off", lab.quote)

    def test_polarity_mismatch_contradicts(self):
        lab = self.lab.label(self.req, "Compliance sign-off is not required before restoring the gateway.")
        self.assertEqual(lab.status, "CONTRADICTS")
        self.assertIn("POLARITY_MISMATCH", lab.reasons)

    def test_low_coverage_unknown(self):
        lab = self.lab.label(self.req, "The cafeteria opens at noon.")
        self.assertEqual(lab.status, "UNKNOWN")
        self.assertIn("LOW_COVERAGE", lab.reasons)

    def test_qualifier_flagged(self):
        lab = self.lab.label(self.req, "Restoring the gateway requires compliance sign-off unless an exception applies.")
        self.assertIn("QUALIFIED", lab.reasons)

    def test_questions_skip_polarity(self):
        q = Requirement("r1", "When did the gateway not restart?", kind="question")
        lab = self.lab.label(q, "The gateway restarted at noon.")
        self.assertNotEqual(lab.status, "CONTRADICTS")

    def test_empty_inputs(self):
        self.assertEqual(self.lab.label(Requirement("r", "the of and"), "text").status, "UNKNOWN")
        self.assertEqual(self.lab.label(self.req, "").status, "UNKNOWN")

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            LexicalLabeler(0)


class LLMLabelerTest(unittest.TestCase):
    req = Requirement("r1", "Sign-off is required.")
    text = "Before restart, compliance sign-off is required.  Nothing else."

    def lab(self, reply):
        return LLMLabeler(lambda prompt: reply).label(self.req, self.text)

    def test_grounded_quote_supports(self):
        lab = self.lab('{"status": "SUPPORTS", "quote": "compliance sign-off is required"}')
        self.assertEqual(lab.status, "SUPPORTS")
        self.assertEqual(self.text[lab.span[0]:lab.span[1]], "compliance sign-off is required")

    def test_whitespace_tolerant_grounding(self):
        lab = self.lab('{"status": "SUPPORTS", "quote": "is required. Nothing"}')
        self.assertEqual(lab.status, "SUPPORTS")

    def test_ungrounded_quote_fails_closed(self):
        lab = self.lab('{"status": "SUPPORTS", "quote": "sign-off was waived"}')
        self.assertEqual((lab.status, lab.reasons), ("UNKNOWN", ("UNGROUNDED_QUOTE",)))

    def test_empty_quote_fails_closed(self):
        self.assertEqual(self.lab('{"status": "CONTRADICTS", "quote": ""}').status, "UNKNOWN")

    def test_malformed_output_fails_closed(self):
        for reply in ("SUPPORTS", '{"status": "YES"}', "{not json}", "", '{"status":"SUPPORTS","quote":5}'):
            self.assertEqual(self.lab(reply).status, "UNKNOWN", reply)

    def test_exception_fails_closed(self):
        def boom(prompt):
            raise TimeoutError
        lab = LLMLabeler(boom).label(self.req, self.text)
        self.assertEqual(lab.reasons, ("LABELER_ERROR", "TimeoutError"))

    def test_json_inside_prose(self):
        lab = self.lab('Sure: {"status": "SUPPORTS", "quote": "sign-off is required"} done')
        self.assertEqual(lab.status, "SUPPORTS")

    def test_prompt_contains_requirement_and_passage(self):
        seen = []
        LLMLabeler(lambda p: seen.append(p) or "{}").label(Requirement("q", "Who?", "question"), "Ada did.")
        self.assertIn("Question: Who?", seen[0])
        self.assertIn("Ada did.", seen[0])

    def test_anthropic_completer_with_stub_client(self):
        calls = []

        class Messages:
            def create(self, **kw):
                calls.append(kw)
                return SimpleNamespace(content=[SimpleNamespace(text='{"status":"UNKNOWN","quote":""}')])

        complete = anthropic_completer(model="m", client=SimpleNamespace(messages=Messages()))
        self.assertIn("UNKNOWN", complete("hi"))
        self.assertEqual((calls[0]["model"], calls[0]["temperature"]), ("m", 0))


class PipelineTest(unittest.TestCase):
    claims = {"r1": "Compliance sign-off is required before restoring the gateway.",
              "r2": {"text": "On-call staff may start automated recovery.", "kind": "claim"}}

    def test_label_evidence_rows_are_gate_ready(self):
        evidence, trace = label_evidence(PACK, self.claims, [
            passage("a", "Restoring the gateway requires compliance sign-off."),
            passage("b", "The cafeteria opens at noon."),
        ], LexicalLabeler(), observed_at="2026-11-02T10:00:00Z")
        self.assertEqual(len(trace), 4)
        self.assertEqual([e["id"] for e in evidence], ["a::r1"])
        self.assertEqual(set(evidence[0]), {"id", "requirement_id", "origin", "source_ref", "status", "observed_at"})

    def test_assess_verdicts(self):
        lab = LexicalLabeler()
        partial = assess(PACK, self.claims, [passage("a", "Restoring the gateway requires compliance sign-off.")],
                         lab, as_of=AS_OF)
        self.assertEqual(partial["verdict"], "INCONCLUSIVE")
        full = assess(PACK, self.claims, [
            passage("a", "Restoring the gateway requires compliance sign-off."),
            passage("b", "On-call staff may start automated recovery after a timeout."),
        ], lab, as_of=AS_OF)
        self.assertEqual(full["verdict"], "ADMIT")
        self.assertEqual(full["labeler"], "lexical@0.6")
        refused = assess(PACK, self.claims, [
            passage("a", "Restoring the gateway requires compliance sign-off."),
            passage("b", "On-call staff may start automated recovery."),
            passage("c", "Compliance sign-off is never required before restoring the gateway."),
        ], lab, as_of=AS_OF)
        self.assertEqual(refused["verdict"], "REFUSE")

    def test_unclaimed_requirement_stays_inconclusive(self):
        out = assess(PACK, {"r1": self.claims["r1"]},
                     [passage("a", "Restoring the gateway requires compliance sign-off.")],
                     LexicalLabeler(), as_of=AS_OF)
        self.assertEqual({f["requirement_id"]: f["verdict"] for f in out["findings"]},
                         {"r1": "ADMIT", "r2": "INCONCLUSIVE"})

    def test_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            label_evidence(PACK, {"r1": 3}, [], LexicalLabeler(), "2026-11-02T10:00:00Z")
        with self.assertRaises(ValueError):
            label_evidence(PACK, self.claims, [{"id": "x", "text": "t"}], LexicalLabeler(), "2026-11-02T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
