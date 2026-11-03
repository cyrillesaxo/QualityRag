"""Trusted-host APX native subprocess boundary tests.

Real APX algorithm execution has its own private-repository test suite.
These tests verify bounded host transport, no fallback, and secret isolation.
"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rct_native_semantic_host import (
    NativeSemanticUnavailable, inspect_native_semantics,
    execute_dual_semantic_check)


class NativeSemanticHostTests(unittest.TestCase):
    def test_missing_original_apx_package_fails_closed(self):
        with self.assertRaises(NativeSemanticUnavailable):
            inspect_native_semantics(
                "The nurse must NOT proceed.",
                "The nurse must proceed.",
                apx_packages_root="/no/such/apx/packages")

    def test_input_limits_and_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            inspect_native_semantics("", "candidate",apx_packages_root="/tmp")
        with self.assertRaises(ValueError):
            inspect_native_semantics("a"*8193,"candidate",apx_packages_root="/tmp")
        with self.assertRaises(ValueError):
            inspect_native_semantics("source","candidate",apx_packages_root="./apx")
        with self.assertRaises(ValueError):
            inspect_native_semantics("source","candidate",
                                     apx_packages_root="/tmp",
                                     timeout_seconds=0)

    def test_node_process_receives_only_selected_environment(self):
        source="A nurse must NOT proceed."
        candidate="A nurse must proceed."
        observed={}
        def invoke(argv, **kwargs):
            from hashlib import sha256
            import json
            observed.update(kwargs)
            native={
                "schema":"qualityrag.native-semantic-transition/v1",
                "original_engine_schema":"apx.semantic-text-transition/v0.1",
                "source_sha256":sha256(source.encode()).hexdigest(),
                "candidate_sha256":sha256(candidate.encode()).hexdigest(),
                "verdict":"REFUSE",
                "observed_changes":[{"kind":"NEGATION","status":"MISSING"}],
                "source_authority":"UNVERIFIED_HEURISTIC",
                "source_coverage":"BOUNDED_ENGLISH_PATTERNS",
                "semantic_completeness":"UNKNOWN",
                "qualityrag_admission":"INCONCLUSIVE",
                "can_generate":False,
            }
            class Result:
                returncode=0
                stdout=json.dumps(native)
            return Result()
        with patch.dict(os.environ,{"QR_PRIVATE_SECRET":"must-never-pass"}):
            with patch("rct_native_semantic_host.subprocess.run",side_effect=invoke):
                receipt=inspect_native_semantics(
                    source,candidate,apx_packages_root="/trusted/apx/packages")
        self.assertEqual(receipt["verdict"],"REFUSE")
        self.assertNotIn("QR_PRIVATE_SECRET",observed["env"])
        self.assertNotIn("NODE_OPTIONS",observed["env"])
        self.assertEqual(set(observed["env"]),
                         {"PATH","APX_PACKAGES_ROOT","RCT_APX_HMAC_KEY_B64"})
        self.assertNotIn("NOT proceed",str(receipt))
        self.assertNotIn("must-never-pass",str(receipt))

    def test_forged_comparator_output_fails_closed(self):
        from unittest.mock import Mock
        result=Mock(returncode=0,stdout='{"verdict":"ADMIT"}')
        with patch("rct_native_semantic_host.subprocess.run",return_value=result):
            with self.assertRaises(NativeSemanticUnavailable):
                inspect_native_semantics(
                    "source","candidate",apx_packages_root="/trusted/root")

    def test_reviewed_source_version_mismatch_rejected_before_process(self):
        with patch("rct_native_semantic_host.inspect_native_semantics") as native:
            with self.assertRaisesRegex(ValueError,"document version"):
                execute_dual_semantic_check(
                    {"source_span_audit":{
                        "source_sha256":"0"*64,
                        "candidate_sha256":"1"*64}},
                    source_text="original",candidate_text="transformed",
                    apx_packages_root="/trusted/apx/packages",
                    ir={},signed_policy={},signed_review={},
                    policy_keys={},reviewer_keys={},minimum_sequence=1,
                    service="example",environment="test",as_of="2026-11-03T00:00:00Z",
                    nonce_accepted=lambda *args: False)
        native.assert_not_called()


if __name__=="__main__":
    unittest.main()
