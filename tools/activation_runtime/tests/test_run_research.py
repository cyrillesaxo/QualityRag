import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.activation_runtime import run_research as rr


class ResearchHarnessTests(unittest.TestCase):
    def test_missing_dependency_is_skip_not_pass(self):
        no_ffmpeg = lambda tool: None if tool == "ffmpeg" else shutil.which(tool)
        with tempfile.TemporaryDirectory() as root:
            report = rr.run(Path(root) / "out", argv=["--out", "x"], which=no_ffmpeg)
        self.assertEqual(report["result"], "INCOMPLETE")
        self.assertEqual(report["skipped"], ["clips", "ablation", "host_device"])
        for name in report["skipped"]:
            self.assertEqual(report["components"][name], {"status": "SKIP", "reason": "DEPENDENCY_UNAVAILABLE:ffmpeg"})
        self.assertIsNone(report["ablation"])
        self.assertEqual(report["components"]["finite"]["status"], "RAN")

    def test_receipt_records_invocation_inputs_and_environment(self):
        no_ffmpeg = lambda tool: None if tool == "ffmpeg" else shutil.which(tool)
        with tempfile.TemporaryDirectory() as root:
            report = rr.run(Path(root) / "out", argv=["--out", "custom"], which=no_ffmpeg)
        self.assertEqual(report["invocation"]["argv"], ["--out", "custom"])
        self.assertIn("fixtures/packspec.json", report["inputs"])
        self.assertIn("research/environment.lock.json", report["inputs"])
        self.assertEqual(report["environment"]["lock_sha256"], report["inputs"]["research/environment.lock.json"])

    def test_environment_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as root:
            lock = Path(root) / "lock.json"
            lock.write_text(json.dumps({"python": "0.0.0", "platform": "Plan9", "machine": "pdp11",
                                        "ffmpeg": None, "node": None, "packages": {"surely-not-installed-pkg": "1.0"}}))
            env = rr.environment(lock, which=lambda tool: None)
        items = {m["item"] for m in env["mismatches"]}
        self.assertFalse(env["matches_lock"])
        self.assertTrue({"python", "platform", "machine", "package:surely-not-installed-pkg"} <= items)
        self.assertEqual(env["missing_tools"], ["ffmpeg", "node"])

    def test_full_run_writes_identical_stdout_and_repeats_structurally(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg unavailable")
        with tempfile.TemporaryDirectory() as root:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rr.main(["--out", str(Path(root) / "a")])
            self.assertEqual((Path(root) / "a/stdout.json").read_text(), out.getvalue())
            first = json.loads((Path(root) / "a/receipt.json").read_text())
            with contextlib.redirect_stdout(io.StringIO()):
                rr.main(["--out", str(Path(root) / "b")])
            second = json.loads((Path(root) / "b/receipt.json").read_text())
        self.assertEqual(first["skipped"], [])
        self.assertEqual(first["components"]["clips"], second["components"]["clips"])
        self.assertEqual(first["inputs"], second["inputs"])
        self.assertEqual(first["result"], second["result"])


if __name__ == "__main__":
    unittest.main()
