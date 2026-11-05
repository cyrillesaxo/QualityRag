"""Direct acceptance checks missing from the software-candidate evidence map."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.activation_runtime.interpreter import execute_plan
from tools.activation_runtime.preservation import audit_output
import test_criterion_behaviors as behaviors


class SoftwareVerificationTests(unittest.TestCase):
    def fixture(self):
        return behaviors.CriterionBehaviorTests().fixture()

    def test_single_changed_obligation_identifies_counterexample_and_clause(self):
        raw, ir, contract = self.fixture()
        changed = {"instruction":"may disclose", "unit":"mg"}
        result = audit_output(raw, changed, contract, current_ir=ir)
        self.assertEqual(result["finite_constraint_result"], "UNSAT")
        self.assertEqual(result["violations"], [
            {"field":"instruction", "reason":"CHANGED_REQUIRED_DISTINCTION"}])
        self.assertEqual(result, audit_output(raw, changed, contract, current_ir=ir))

    def test_finite_interpreter_language_rejects_code_and_bounds_work(self):
        raw, ir, contract = self.fixture()
        forbidden = [{"op":"EVAL","code":"raise SystemExit"},
                     {"op":"IMPORT","module":"os"},
                     {"op":"ACTIVATE","runtime":"os.system"},
                     {"op":"VERIFY","callback":"os.system"}]
        for operator in forbidden:
            with self.subTest(operator=operator), self.assertRaises(ValueError):
                execute_plan(raw, plan=[operator], contract=contract, ir=ir)
        with self.assertRaises(ValueError):
            execute_plan(raw, plan=[{"op":"VERIFY"}] * 33, contract=contract, ir=ir)
        result = execute_plan(raw, plan=[{"op":"VERIFY"}], contract=contract, ir=ir)
        self.assertEqual(result["finite_constraint_result"], "SAT")
        self.assertFalse(result["can_generate"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg profile unavailable")
    def test_actual_encoder_measures_bytes_time_model_and_raw_fallback(self):
        from tools.activation_runtime.scene_codec import encode, train_model, canon, frames, decode_frames
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "actual.mkv"
            subprocess.run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i",
                            "testsrc2=size=32x32:rate=4","-t","0.5","-c:v","ffv1",str(source)],
                           check=True, capture_output=True, timeout=30)
            model = train_model([source])
            payload, receipt = encode(source, model)
            self.assertGreater(receipt["encode_ns"], 0)
            self.assertEqual(receipt["payload_bytes"], len(canon(payload)))
            self.assertEqual(receipt["model_bytes"], len(canon(model)))
            self.assertEqual(receipt["fallback_ratio"],
                             sum(r["mode"] == "raw" for r in payload["frames"]) / payload["frame_count"])
            self.assertEqual(decode_frames(payload, model), frames(source)["frames"])
            self.assertEqual(receipt["qualityrag_admission"], "INCONCLUSIVE")

    def test_key_lifecycle_and_version_floor_are_documented(self):
        root = Path(__file__).resolve().parents[3]
        signed = (root / "tools/packspec_compiler/SIGNED-BUNDLES.md").read_text()
        closure = (root / "docs/STORY-CLOSURE-PACKETS.md").read_text()
        self.assertIn("minimum accepted policy sequence", signed)
        self.assertIn("Missing/revoked keys", signed)
        self.assertIn("retired_at", closure)
        self.assertIn("compromised", closure)

