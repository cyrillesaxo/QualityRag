"""Policy tester, governance advisor and replay, on the real enterprise-rag EU payments scenario."""
import base64
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.activation_runtime import governance as g
from tools.activation_runtime.authority import issue_access
from tools.activation_runtime.gardener import Gardener
from tools.activation_runtime.service import Application

AT = "2026-11-05T12:00:00Z"


class PolicyTesterTests(unittest.TestCase):
    def setUp(self):
        self.ex = g.example()
        self.test = g.policy_test(self.ex["pack"], self.ex["documents"], self.ex["retrieved"], as_of=self.ex["as_of"])

    def req(self, rid):
        return next(r for r in self.test["requirements"] if r["requirement_id"] == rid)

    def test_verdict_matches_the_demo(self):
        self.assertEqual(self.test["verdict"], "ADMIT")
        initial = g.policy_test(self.ex["pack"], self.ex["documents"],
                                ["ops-7.3", "incident-summary", "runbook-restart", "ops-mirror-7.3"], as_of=self.ex["as_of"])
        self.assertEqual(initial["verdict"], "INCONCLUSIVE")
        self.assertEqual(sum(r["verdict"] == "INCONCLUSIVE" for r in initial["requirements"]), 2)

    def test_copies_collapse_to_one_origin(self):
        r = self.req("recovery-procedure")
        self.assertEqual(r["independent_sources"], 1)
        spans = {s["chunk_id"]: s for s in r["spans"]}
        self.assertTrue(spans["ops-7.3"]["counts_as_origin"])
        self.assertFalse(spans["ops-mirror-7.3"]["counts_as_origin"])
        self.assertEqual(spans["ops-mirror-7.3"]["same_origin_as"], "ops-7.3")
        self.assertEqual(self.test["dependent_groups"][0]["origin"], "ops-handbook")

    def test_qualifiers_are_flagged_not_evaluated(self):
        words = lambda rid: [q["word"] for s in self.req(rid)["spans"] for q in s["qualifiers"]]
        self.assertEqual(words("eu-screening-control"), ["unless"])
        self.assertEqual(words("applicable-approval-or-exception"), ["only"])
        self.assertEqual(words("recovery-procedure"), [])
        self.assertEqual(self.req("eu-screening-control")["verdict"], "ADMIT")
        self.assertEqual(self.test["summary"]["qualified_requirements"], 2)

    def test_unlinked_chunks_are_listed(self):
        self.assertEqual(sorted(u["chunk_id"] for u in self.test["unlinked"]), ["incident-summary", "runbook-restart"])

    def test_stale_span_does_not_count(self):
        pack = json.loads(json.dumps(self.ex["pack"]))
        pack["requirements"][0]["max_age_seconds"] = 60
        docs = json.loads(json.dumps(self.ex["documents"]))
        docs[0]["observed_at"] = "2026-01-01T00:00:00Z"
        r = next(x for x in g.policy_test(pack, docs, self.ex["retrieved"], as_of=self.ex["as_of"])["requirements"]
                 if x["requirement_id"] == "recovery-procedure")
        spans = {s["chunk_id"]: s for s in r["spans"]}
        self.assertFalse(spans["ops-7.3"]["counts_as_origin"])   # stale
        self.assertTrue(spans["ops-mirror-7.3"]["counts_as_origin"])  # same origin, fresh copy

    def test_rejects_bad_input(self):
        for args in [(self.ex["pack"], self.ex["documents"], ["nope"]), (self.ex["pack"], [], ["ops-7.3"]),
                     ({"id": "x"}, self.ex["documents"], ["ops-7.3"])]:
            with self.assertRaises(ValueError):
                g.policy_test(*args, as_of=AT)

    def test_qualifier_matching(self):
        self.assertEqual([q["word"] for q in g.qualifiers("Allowed only if approved, unless not documented.")],
                         ["only if", "unless", "not"])
        self.assertEqual(g.qualifiers("Notably, the knot holds."), [])


class AdvisorTests(unittest.TestCase):
    def setUp(self):
        self.ex = g.example()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.empty_trust = Path(temp.name) / "trust.json"
        self.empty_trust.write_text(json.dumps({"schema": "qualityrag.reviewer-trust/v1", "reviewers": []}))
        self.test = g.policy_test(self.ex["pack"], self.ex["documents"], self.ex["retrieved"], as_of=self.ex["as_of"])

    def ids(self, result):
        return [f["id"] for f in result["findings"]]

    def test_findings_on_the_scenario(self):
        result = g.advise(trust_path=self.empty_trust, pack=self.ex["pack"], test=self.test,
                          benchmark={"false_admission_rate": 0.602, "answer_rate": 0.773, "n": 1000, "labeler": "lexical@0.6"})
        self.assertEqual(self.ids(result), ["calibration.false-admission", "trust.no-active-reviewer",
                                            "evidence.qualified-support", "pack.single-origin", "pack.no-max-age"])
        self.assertEqual(result["counts"], {"ERROR": 2, "WARN": 2, "INFO": 1})
        self.assertTrue(result["blocks_promotion"])
        single = next(f for f in result["findings"] if f["id"] == "pack.single-origin")
        self.assertIn("ops-7.3 and ops-mirror-7.3", single["checked"])

    def test_trust_store_with_active_key_clears_the_error(self):
        key = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "trust.json"
            path.write_text(json.dumps({"schema": "qualityrag.reviewer-trust/v1", "reviewers": [
                {"key_id": "r1", "github_login": "reviewer", "status": "active", "valid_from": "2026-01-01T00:00:00Z", "public_key": key}]}))
            self.assertNotIn("trust.no-active-reviewer", self.ids(g.advise(trust_path=path)))
            path.write_text("{}")
            self.assertEqual(self.ids(g.advise(trust_path=path)), ["trust.unreadable"])

    def test_benchmark_under_limit_and_invalid(self):
        self.assertNotIn("calibration.false-admission",
                         self.ids(g.advise(trust_path=self.empty_trust, benchmark={"false_admission_rate": 0.05, "answer_rate": 0.6, "n": 100})))
        with self.assertRaises(ValueError):
            g.advise(trust_path=self.empty_trust, benchmark={"false_admission_rate": "high", "answer_rate": 0.6, "n": 100})

    def test_open_challenge_from_garden(self):
        with tempfile.TemporaryDirectory() as d:
            garden = Gardener(str(Path(d) / "g.sqlite"))
            ev = lambda i, op, b, parents=(): garden.append(event_id=i, operation=op, branch=b, actor="r", source_sha256="a" * 64,
                                                           source_ref="t", statement="statement " + i, at=AT, parents=parents)
            ev("e1", "PROPOSE", "gate"); ev("e2", "PROPOSE", "llm", ["gate"]); ev("e3", "CHALLENGE", "llm")
            ev("e4", "CHALLENGE", "gate")
            state = garden.replay()
            garden.close()
        result = g.advise(trust_path=self.empty_trust, garden=state)
        self.assertEqual([i for i in self.ids(result) if i.startswith("gardener")],
                         ["gardener.open-challenge.gate", "gardener.open-challenge.llm"])


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.ex = g.example()

    def test_branch_diff_on_the_scenario(self):
        r = g.replay(self.ex["pack"], self.ex["branch_pack"], self.ex["cases"], as_of=self.ex["as_of"])
        self.assertEqual(r["pack_diff"], [{"requirement_id": "recovery-procedure", "change": "modified",
                                           "field": "min_independent_sources", "from": 1, "to": 2}])
        self.assertEqual((r["base"]["admit"], r["branch"]["admit"]), (1, 0))
        self.assertEqual([(f["id"], f["from"], f["to"], f["effect"]) for f in r["flips"]],
                         [("targeted-retrieval", "ADMIT", "INCONCLUSIVE", "unlabeled")])
        self.assertIsNone(r["base"]["answer_rate"])

    def test_labeled_effects_and_rates(self):
        full = self.ex["cases"][1]["evidence"]
        two = full + [{"id": "x", "requirement_id": "recovery-procedure", "origin": "independent-sre-wiki",
                       "source_ref": "wiki#x", "status": "SUPPORTS", "observed_at": "2026-11-02T10:00:00Z"}]
        cases = [{"id": "wrong", "evidence": full, "expect_admit": False},
                 {"id": "right", "evidence": full, "expect_admit": True},
                 {"id": "kept", "evidence": two, "expect_admit": True}]
        r = g.replay(self.ex["pack"], self.ex["branch_pack"], cases, as_of=self.ex["as_of"])
        self.assertEqual(r["effects"]["false_admission_removed"], 1)
        self.assertEqual(r["effects"]["correct_answer_lost"], 1)
        self.assertEqual((r["base"]["answer_rate"], r["branch"]["answer_rate"]), (1.0, 0.5))
        self.assertEqual((r["base"]["false_admission_rate"], r["branch"]["false_admission_rate"]), (1.0, 0.0))

    def test_rejects_bad_cases(self):
        for cases in [[], [{"id": "a", "evidence": []}, {"id": "a", "evidence": []}],
                      [{"id": "a", "evidence": [], "expect_admit": "yes"}], [{"id": "a", "evidence": [], "extra": 1}]]:
            with self.assertRaises(ValueError):
                g.replay(self.ex["pack"], self.ex["branch_pack"], cases, as_of=AT)


class ServiceRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.key = Ed25519PrivateKey.generate()
        self.app = Application(self.temp.name, access_keys={"issuer": self.key.public_key()}, release_keys={}, clock=lambda: AT)

    def auth(self, scopes):
        token = issue_access(subject="dev", tenant="lab", scopes=scopes, key=self.key, key_id="issuer",
                             issued_at="2026-11-04T00:00:00Z", expires_at="2026-11-06T00:00:00Z")
        return "Bearer " + base64.urlsafe_b64encode(json.dumps(token).encode()).decode().rstrip("=")

    def test_read_scope_runs_all_routes(self):
        a = self.auth(["read"])
        ex = self.app.dispatch("policy/example", {}, a)
        test = self.app.dispatch("policy/test", {k: ex[k] for k in ("pack", "documents", "retrieved", "question", "as_of")}, a)
        self.assertEqual(test["verdict"], "ADMIT")
        advice = self.app.dispatch("policy/advise", {"pack": ex["pack"], "test": test}, a)
        self.assertIn("pack.single-origin", [f["id"] for f in advice["findings"]])
        replay = self.app.dispatch("policy/replay", {"base": ex["pack"], "branch": ex["branch_pack"], "cases": ex["cases"]}, a)
        self.assertEqual(replay["flipped"], 1)

    def test_unknown_options_and_no_token(self):
        a = self.auth(["read"])
        with self.assertRaises(ValueError):
            self.app.dispatch("policy/test", {"pack": {}, "documents": [], "retrieved": [], "labeler": "x"}, a)
        with self.assertRaises(ValueError):
            self.app.dispatch("policy/advise", {"far_limit": 2}, a)
        with self.assertRaises(PermissionError):
            self.app.dispatch("policy/example", {}, None)


if __name__ == "__main__":
    unittest.main()
