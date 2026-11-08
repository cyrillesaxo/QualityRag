"""Offline evidence receipt verification: accept honest replay, reject misleading proof."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from qualityrag import evaluate
from qualityrag.verify_receipt import (
    ReceiptVerificationError, _hash, main, verify_package
)

AS_OF = "2026-11-08T18:00:00.000Z"
WITNESS_AT = "2026-11-08T17:59:59.000Z"


def witness(i, origin, status="SUPPORTS"):
    return {
        "id": "ev_" + format(i, "032x"),
        "requirement_id": "two-source",
        "origin": "org_" + format(origin, "032x"),
        "source_ref": "src_" + format(i, "032x"),
        "status": status,
        "observed_at": WITNESS_AT,
    }


def make_package(evidence=None):
    pack = {
        "id": "signed-off-demo",
        "version": "1",
        "requirements": [{"id": "two-source", "min_independent_sources": 2}],
    }
    sources = evidence if evidence is not None else [witness(1, 1), witness(2, 1)]
    payload = {
        "schema": "qualityrag.evidence-replay/v1",
        "evaluationId": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
        "serviceId": "claims-api",
        "environment": "dev",
        "requestId": "test-001",
        "traceId": "trace-001",
        "asOf": AS_OF,
        "evaluator": "qualityrag.registry-metadata-gate/v1",
        "policy": pack,
        "policySha256": _hash(pack),
        "evidence": sources,
        "expectedResult": evaluate(pack, sources, as_of=AS_OF),
        "sourceOriginStatus": "CALLER_DECLARED_NOT_AUTHENTICATED",
        "ledgerRecordHash": "f" * 64,
    }
    return {
        "payload": payload,
        "integrity": {
            "sha256": _hash(payload),
            "externallyAnchored": False,
            "digitallySigned": False,
            "authenticityVerified": False,
        },
    }


def recompute_hash(package):
    package["integrity"]["sha256"] = _hash(package["payload"])


class OfflineReceiptTest(unittest.TestCase):
    def test_valid_duplicate_origin_and_independent_origin(self):
        before = verify_package(make_package())
        self.assertTrue(before["verified"])
        self.assertEqual(before["verdict"], "INCONCLUSIVE")
        self.assertFalse(before["sourceAuthenticityVerified"])
        self.assertFalse(before["trustedExportDigestMatched"])
        after = verify_package(make_package([witness(1, 1), witness(2, 2)]))
        self.assertEqual(after["verdict"], "ADMIT")

    def test_contract_verdict_not_a_truth_claim(self):
        pkg = make_package()
        result = verify_package(pkg)
        self.assertFalse(result["customerIdentityVerified"])
        self.assertFalse(result["complianceCertified"])
        self.assertFalse(result["ledgerChainIndependentlyVerified"])

    def test_policy_and_receipt_out_of_band_hash_pinning(self):
        pkg = make_package()
        digest = pkg["integrity"]["sha256"]
        policy_digest = pkg["payload"]["policySha256"]
        result = verify_package(
            pkg, trusted_sha256=digest, trusted_policy_sha256=policy_digest
        )
        self.assertTrue(result["trustedPolicyDigestMatched"])
        with self.assertRaisesRegex(ReceiptVerificationError, "TRUSTED_EXPORT"):
            verify_package(pkg, trusted_sha256="0" * 64)
        with self.assertRaisesRegex(ReceiptVerificationError, "TRUSTED_POLICY"):
            verify_package(pkg, trusted_policy_sha256="0" * 64)

    def test_changed_verdict_fails_even_when_export_hash_rewritten(self):
        pkg = make_package()
        pkg["payload"]["expectedResult"]["verdict"] = "ADMIT"
        recompute_hash(pkg)
        with self.assertRaisesRegex(ReceiptVerificationError, "INDEPENDENT_REPLAY_MISMATCH"):
            verify_package(pkg)

    def test_missing_source_with_modified_pack_digest_fails_pinned_hash(self):
        pkg = make_package()
        old = pkg["payload"]["policySha256"]
        pkg["payload"]["policy"]["requirements"][0]["min_independent_sources"] = 1
        pkg["payload"]["policySha256"] = _hash(pkg["payload"]["policy"])
        pkg["payload"]["expectedResult"] = evaluate(
            pkg["payload"]["policy"], pkg["payload"]["evidence"], as_of=AS_OF
        )
        recompute_hash(pkg)
        self.assertEqual(verify_package(pkg)["verdict"], "ADMIT")
        with self.assertRaisesRegex(ReceiptVerificationError, "TRUSTED_POLICY"):
            verify_package(pkg, trusted_policy_sha256=old)

    def test_damaged_policy_digest_rejected(self):
        pkg = make_package()
        pkg["payload"]["policySha256"] = "0" * 64
        recompute_hash(pkg)
        with self.assertRaisesRegex(ReceiptVerificationError, "POLICY_DIGEST_MISMATCH"):
            verify_package(pkg)

    def test_unsupported_semantic_obligation_refused(self):
        pkg = make_package()
        pkg["payload"]["policy"]["requirements"][0]["requires_authority"] = True
        pkg["payload"]["policySha256"] = _hash(pkg["payload"]["policy"])
        recompute_hash(pkg)
        with self.assertRaisesRegex(ReceiptVerificationError, "UNSUPPORTED_REQUIREMENT"):
            verify_package(pkg)

    def test_duplicated_json_keys_rejected_by_cli(self):
        data = b'{"payload":{}, "payload":{}, "integrity":{}}'
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "receipt.json"
            source.write_bytes(data)
            with contextlib.redirect_stderr(io.StringIO()) as captured:
                result = main([str(source)])
            self.assertEqual(result, 2)
            self.assertIn("DUPLICATE_JSON_KEY", captured.getvalue())

    def test_cli_works_offline(self):
        pkg = make_package()
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "receipt.json"
            source.write_text(json.dumps(pkg), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                result = main([
                    str(source), "--trusted-sha256", pkg["integrity"]["sha256"]
                ])
            self.assertEqual(result, 0)
            self.assertIn('"verified": true', captured.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
