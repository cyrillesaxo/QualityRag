import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from tools.activation_runtime import story_completion as sc

COMMIT = "a" * 40
MERGE = "b" * 40
CI = "https://github.com/cyrillesaxo/QualityRag/actions/runs/1"
RECEIPT = "c" * 64
ISSUED, EXPIRES, AS_OF = "2026-11-05T00:00:00Z", "2026-12-01T00:00:00Z", "2026-11-10T00:00:00Z"


class StoryCompletionTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()  # test-only key
        self.trust = {"reviewer-1": self.key.public_key()}

    def receipt(self, story="US-034", attest=True, **kw):
        return sc.draft(story, implementation_commit=COMMIT, merge_commit=MERGE, ci_url=CI,
                        ci_receipt_sha256=RECEIPT, attest_all_criteria_met=attest, **kw)

    def envelope(self, receipt=None):
        return sc.sign_receipt(receipt or self.receipt(), self.key, key_id="reviewer-1",
                               issued_at=ISSUED, expires_at=EXPIRES)

    def test_signed_receipt_passes_audit_completion_check(self):
        result = sc.verify("US-034", self.envelope(), implementation_commit=COMMIT,
                           trusted_keys=self.trust, as_of=AS_OF)
        self.assertEqual(result["envelope"], "VALID_FOR_AUDIT")

    def test_refuses_to_sign_without_explicit_attestation(self):
        with self.assertRaises(ValueError):
            self.envelope(self.receipt(attest=False))

    def test_untrusted_key_refused(self):
        with self.assertRaises(Exception):
            sc.verify("US-034", self.envelope(), implementation_commit=COMMIT,
                      trusted_keys={"reviewer-1": Ed25519PrivateKey.generate().public_key()}, as_of=AS_OF)

    def test_receipt_bound_to_story_and_commit(self):
        env = self.envelope()
        with self.assertRaises(ValueError):
            sc.verify("US-035", env, implementation_commit=COMMIT, trusted_keys=self.trust, as_of=AS_OF)
        with self.assertRaises(ValueError):
            sc.verify("US-034", env, implementation_commit="d" * 40, trusted_keys=self.trust, as_of=AS_OF)

    def test_expired_receipt_refused(self):
        with self.assertRaises(Exception):
            sc.verify("US-034", self.envelope(), implementation_commit=COMMIT,
                      trusted_keys=self.trust, as_of="2026-12-02T00:00:00Z")

    def test_module_change_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            caps = json.loads(sc.CAPABILITIES.read_text())
            path = Path(d) / "capabilities.json"
            path.write_text(json.dumps(caps))
            receipt = self.receipt(capabilities=path)
            env = sc.sign_receipt(receipt, self.key, key_id="reviewer-1", issued_at=ISSUED,
                                  expires_at=EXPIRES, capabilities=path)
            story = next(s for s in caps["stories"] if s["story_id"] == "US-034")
            story["modules"][0]["sha256"] = "0" * 64
            path.write_text(json.dumps(caps))
            with self.assertRaises(ValueError):
                sc.verify("US-034", env, implementation_commit=COMMIT, trusted_keys=self.trust,
                          as_of=AS_OF, capabilities=path)
            with self.assertRaises(ValueError):  # stale draft cannot be signed either
                sc.sign_receipt(receipt, self.key, key_id="reviewer-1", issued_at=ISSUED,
                                expires_at=EXPIRES, capabilities=path)

    def test_done_story_and_bad_inputs_refused(self):
        with self.assertRaises(ValueError):
            self.receipt("US-001")
        with self.assertRaises(ValueError):
            sc.draft("US-034", implementation_commit="short", merge_commit=MERGE, ci_url=CI,
                     ci_receipt_sha256=RECEIPT)
        with self.assertRaises(ValueError):
            sc.draft("US-034", implementation_commit=COMMIT, merge_commit=MERGE,
                     ci_url="https://evil.example/run", ci_receipt_sha256=RECEIPT)

    def test_trust_store_round_trip_and_cli(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "key.pem").write_bytes(self.key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
            entry = sc.public_key_entry(sc._load_private_key(d / "key.pem"), "reviewer-1", "Reviewer One")
            (d / "trust.json").write_text(json.dumps({"schema": sc.TRUST_SCHEMA, "reviewers": [entry]}))
            keys = sc.load_trust(d / "trust.json")
            (d / "receipt.json").write_text(json.dumps(self.receipt()))
            import contextlib, io
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                sc.main(["sign", "--receipt", str(d / "receipt.json"), "--key", str(d / "key.pem"),
                         "--key-id", "reviewer-1", "--issued-at", ISSUED, "--expires-at", EXPIRES])
            (d / "env.json").write_text(out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                sc.main(["verify", "--story", "US-034", "--implementation-commit", COMMIT,
                         "--envelope", str(d / "env.json"), "--trust", str(d / "trust.json"), "--as-of", AS_OF])
            self.assertEqual(json.loads(out.getvalue())["envelope"], "VALID_FOR_AUDIT")
            self.assertIn("reviewer-1", keys)

    def test_repository_trust_store_is_empty_and_valid(self):
        self.assertEqual(sc.load_trust(), {})


if __name__ == "__main__":
    unittest.main()


class ClosurePacketTests(unittest.TestCase):
    def test_packets_cover_every_open_story_and_doc_is_current(self):
        from tools.activation_runtime import closure_packets as cp
        text = cp.render()
        caps = json.loads(sc.CAPABILITIES.read_text())
        open_ids = [s["story_id"] for s in caps["stories"] if s["status"] != "DONE"]
        for sid in open_ids:
            self.assertIn("### " + sid + " ", text)
        self.assertEqual(text.count("\n### US-"), len(open_ids))
        self.assertEqual(cp.DOC.read_text(), text,
                         "run: python -m tools.activation_runtime.closure_packets")
