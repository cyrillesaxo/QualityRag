import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from tools.activation_runtime import audit as audit_module
from tools.activation_runtime import story_completion as sc

REPO = "cyrillesaxo/QualityRag"
COMMIT, MERGE = "a" * 40, "b" * 40
CI = f"https://github.com/{REPO}/actions/runs/1"
RECEIPT = "c" * 64
CI_DONE = "2026-11-04T00:00:00Z"
ISSUED, EXPIRES, AS_OF = "2026-11-05T00:00:00Z", "2026-12-01T00:00:00Z", "2026-11-10T00:00:00Z"
ROOT = Path(__file__).resolve().parents[3]


def github(overrides=None):
    responses = {
        "/actions/runs/1": {"head_sha": COMMIT, "status": "completed", "conclusion": "success",
                            "repository": {"full_name": REPO}, "updated_at": CI_DONE},
        f"/compare/{COMMIT}...{MERGE}": {"status": "ahead"},
        f"/compare/{MERGE}...main": {"status": "identical"},
        f"/commits/{COMMIT}": {"author": {"login": "story-author"}},
    }
    responses.update(overrides or {})

    def fetch(path):
        if path not in responses:
            raise ValueError("unexpected GitHub request " + path)
        return copy.deepcopy(responses[path])
    return fetch


class StoryCompletionTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()  # test-only key
        self.trust_file = Path(tempfile.mkdtemp()) / "trust.json"
        self.addCleanup(shutil.rmtree, self.trust_file.parent)
        self.write_trust()

    def write_trust(self, **changes):
        entry = sc.public_key_entry(self.key, "reviewer-1", "independent-reviewer", "2026-11-01T00:00:00Z")
        entry.update(changes)
        self.trust_file.write_text(json.dumps({"schema": sc.TRUST_SCHEMA, "reviewers": [entry]}))
        return sc.load_trust(self.trust_file)

    def receipt(self, story="US-034", attest=True, **kw):
        return sc.draft(story, implementation_commit=COMMIT, merge_commit=MERGE, ci_url=CI,
                        ci_receipt_sha256=RECEIPT, attest_all_criteria_met=attest, **kw)

    def envelope(self, receipt=None, issued=ISSUED, expires=EXPIRES, **kw):
        return sc.sign_receipt(receipt or self.receipt(), self.key, key_id="reviewer-1",
                               issued_at=issued, expires_at=expires, **kw)

    def check(self, envelope=None, *, trust=None, as_of=AS_OF, fetch=None, story="US-034", commit=COMMIT, **kw):
        return sc.verify(story, envelope or self.envelope(), implementation_commit=commit,
                         trust=trust if trust is not None else sc.load_trust(self.trust_file), as_of=as_of, _fetch=fetch or github(), **kw)

    def test_valid_receipt_passes(self):
        result = self.check()
        self.assertEqual((result["envelope"], result["ci_run"]), ("VALID_FOR_AUDIT", 1))

    def test_receipt_is_historical_not_expiring(self):
        # Verified long after its 30-day signature window: completion records do not lapse.
        self.assertEqual(self.check(as_of="2028-01-01T00:00:00Z")["envelope"], "VALID_FOR_AUDIT")

    def test_issue_time_bounded_by_evidence(self):
        with self.assertRaisesRegex(ValueError, "predates its CI evidence"):
            self.check(self.envelope(issued="2026-11-03T00:00:00Z", expires="2026-11-20T00:00:00Z"))
        with self.assertRaisesRegex(ValueError, "future"):
            self.check(as_of="2026-11-04T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "predates the reviewer key"):
            self.check(trust=self.write_trust(valid_from="2026-11-06T00:00:00Z"))

    def test_key_lifecycle(self):
        retired = self.write_trust(status="retired", retired_at="2026-11-06T00:00:00Z")
        self.assertEqual(self.check(trust=retired, as_of="2027-06-01T00:00:00Z")["envelope"], "VALID_FOR_AUDIT")
        retired_early = self.write_trust(status="retired", retired_at="2026-11-04T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "retired"):
            self.check(trust=retired_early)
        with self.assertRaisesRegex(ValueError, "compromised"):
            self.check(trust=self.write_trust(status="compromised"))
        with self.assertRaisesRegex(ValueError, "untrusted"):
            self.check(trust={})
        other = sc.public_key_entry(Ed25519PrivateKey.generate(), "reviewer-1", "x", "2026-11-01T00:00:00Z")
        self.trust_file.write_text(json.dumps({"schema": sc.TRUST_SCHEMA, "reviewers": [other]}))
        with self.assertRaises(Exception):
            self.check()

    def test_github_evidence_must_hold(self):
        cases = {
            "/actions/runs/1": {"head_sha": "d" * 40, "status": "completed", "conclusion": "success",
                                "repository": {"full_name": REPO}, "updated_at": CI_DONE},
            f"/compare/{COMMIT}...{MERGE}": {"status": "diverged"},
            f"/compare/{MERGE}...main": {"status": "behind"},
        }
        for path, response in cases.items():
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.check(fetch=github({path: response}))
        failed = dict(cases["/actions/runs/1"], head_sha=COMMIT, conclusion="failure")
        with self.assertRaises(ValueError):
            self.check(fetch=github({"/actions/runs/1": failed}))

    def test_reviewer_must_not_be_author(self):
        with self.assertRaisesRegex(ValueError, "independent"):
            self.check(fetch=github({f"/commits/{COMMIT}": {"author": {"login": "Independent-Reviewer"}}}))
        with self.assertRaisesRegex(ValueError, "independent"):
            self.check(fetch=github({f"/commits/{COMMIT}": {"author": None}}))

    def test_bound_to_story_commit_and_ci_url(self):
        env = self.envelope()
        with self.assertRaises(ValueError):
            self.check(env, story="US-035")
        with self.assertRaises(ValueError):
            self.check(env, commit="d" * 40)
        foreign = sc.draft("US-034", implementation_commit=COMMIT, merge_commit=MERGE,
                           ci_url="https://github.com/someone/else/actions/runs/1",
                           ci_receipt_sha256=RECEIPT, attest_all_criteria_met=True)
        with self.assertRaisesRegex(ValueError, "CI evidence"):
            self.check(self.envelope(foreign))

    def test_refuses_to_sign_without_explicit_attestation(self):
        with self.assertRaises(ValueError):
            self.envelope(self.receipt(attest=False))

    def test_module_change_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            caps = json.loads(sc.CAPABILITIES.read_text())
            path = Path(d) / "capabilities.json"
            path.write_text(json.dumps(caps))
            receipt = self.receipt(capabilities=path)
            env = self.envelope(receipt, capabilities=path)
            next(s for s in caps["stories"] if s["story_id"] == "US-034")["modules"][0]["sha256"] = "0" * 64
            path.write_text(json.dumps(caps))
            with self.assertRaises(ValueError):
                self.check(env, capabilities=path)
            with self.assertRaises(ValueError):
                self.envelope(receipt, capabilities=path)

    def test_done_story_and_bad_inputs_refused(self):
        with self.assertRaises(ValueError):
            self.receipt("US-002")  # already DONE
        with self.assertRaises(ValueError):
            sc.draft("US-034", implementation_commit="short", merge_commit=MERGE, ci_url=CI, ci_receipt_sha256=RECEIPT)
        with self.assertRaises(ValueError):
            sc.draft("US-034", implementation_commit=COMMIT, merge_commit=MERGE,
                     ci_url="https://evil.example/run", ci_receipt_sha256=RECEIPT)

    def test_trust_store_validation(self):
        bad = [{"github_login": ""}, {"status": "retired"}, {"status": "active", "retired_at": "2026-12-01T00:00:00Z"},
               {"status": "unknown"}, {"valid_from": "yesterday"},
               {"status": "retired", "retired_at": "2026-10-01T00:00:00Z"}]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.write_trust(**change)
        self.assertEqual(sc.load_trust(), {})  # repository store starts empty

    def test_cli_sign_verify_and_attach_then_audit(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "key.pem").write_bytes(self.key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                sc.main(["pubkey", "--key", str(d / "key.pem"), "--key-id", "reviewer-1",
                         "--github-login", "independent-reviewer", "--valid-from", "2026-11-01T00:00:00Z"])
            self.assertEqual(json.loads(out.getvalue())["status"], "active")
            (d / "receipt.json").write_text(json.dumps(self.receipt()))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                sc.main(["sign", "--receipt", str(d / "receipt.json"), "--key", str(d / "key.pem"),
                         "--key-id", "reviewer-1", "--issued-at", ISSUED, "--expires-at", EXPIRES])
            envelope = json.loads(out.getvalue())

            # Attach into a minimal copy of the repository and audit it with the trust store.
            root = d / "repo"
            caps = json.loads(sc.CAPABILITIES.read_text())
            for story in caps["stories"]:
                for module in story["modules"]:
                    target = root / module["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / module["path"], target)
                    module["sha256"] = __import__("hashlib").sha256(target.read_bytes()).hexdigest()
                if story["story_id"] in ("US-001", "US-002"):
                    story["status"] = "IN_REVIEW"  # their live-GitHub acceptance is tested elsewhere
            shutil.copyfile(ROOT / "FR.MD", root / "FR.MD")
            capabilities = root / "tools/activation_runtime/capabilities.json"
            capabilities.write_text(json.dumps(caps, indent=2) + "\n")
            trust = sc.load_trust(self.trust_file)
            sc.attach("US-034", envelope, implementation_commit=COMMIT, trust=trust,
                      capabilities=capabilities, _fetch=github())
            result = audit_module.audit(root, trust=trust, as_of=AS_OF, _fetch=github())
            self.assertEqual(result["counts"]["DONE"], 1)
            self.assertEqual(result["signed_completions"][0]["story_id"], "US-034")
            with self.assertRaisesRegex(ValueError, "untrusted"):
                audit_module.audit(root, trust={}, as_of=AS_OF, _fetch=github())


class ClosurePacketTests(unittest.TestCase):
    def test_packets_cover_every_open_story_and_doc_is_current(self):
        from tools.activation_runtime import closure_packets as cp
        text = cp.render()
        caps = json.loads(sc.CAPABILITIES.read_text())
        open_ids = [s["story_id"] for s in caps["stories"] if s["status"] != "DONE"]
        for sid in open_ids:
            self.assertIn("### " + sid + " ", text)
        self.assertEqual(text.count("\n### US-"), len(open_ids))
        self.assertEqual(cp.DOC.read_text(), text, "run: python -m tools.activation_runtime.closure_packets")


if __name__ == "__main__":
    unittest.main()


class CriteriaMapTests(unittest.TestCase):
    def test_every_cited_test_exists(self):
        import ast
        from tools.activation_runtime import closure_packets as cp
        cmap = cp.load_criteria()
        tests_dir = ROOT / "tools/activation_runtime/tests"
        names = {}
        for path in tests_dir.glob("test_*.py"):
            names[path.stem] = {n.name for n in ast.walk(ast.parse(path.read_text()))
                                if isinstance(n, ast.FunctionDef) and n.name.startswith("test")}
        for sid, rows in cmap.items():
            for row in rows:
                for ref in row.get("evidence", []):
                    with self.subTest(story=sid, ref=ref):
                        if ref.startswith("semantic_store/"):
                            self.assertTrue((ROOT / "tools/semantic_store/tests" / (ref.split("/", 1)[1] + ".py")).exists())
                        else:
                            module, _, test = ref.partition(".")
                            self.assertIn(test, names.get(module, set()))
                if row["status"] == "TESTED" and row["kind"] in ("SOFTWARE", "DOCUMENT") and sid != "US-022":
                    self.assertTrue(row.get("evidence"), f"{sid}.{row['n']} is TESTED without a cited test")
