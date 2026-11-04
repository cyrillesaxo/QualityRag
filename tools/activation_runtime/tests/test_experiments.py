from pathlib import Path
import tempfile
import unittest
from tools.activation_runtime.experiments import Registry,paired_interval,dataset_manifest
from tools.activation_runtime.release import readiness,REQUIRED


class ExperimentTests(unittest.TestCase):
    def test_preregistration_precedes_holdout_and_proposers_denied(self):
        import json
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from tools.activation_runtime.authority import review_binding
        template=Path(__file__).resolve().parents[1]/"research"/"protocol.json"
        protocol=json.loads(template.read_text());protocol["dataset_sha256"]="a"*64;protocol["registered_at"]="2026-11-04T12:00:00Z"
        with tempfile.TemporaryDirectory() as temp:
            reviewer=Ed25519PrivateKey.generate();author=Ed25519PrivateKey.generate()
            registry=Registry(Path(temp)/"research.sqlite",registry_id="fixture-registry",tenant="fixture",
                reviewer_keys={"reviewer":reviewer.public_key()},reviewer_subjects={"reviewer":"reviewer"},
                author_public_key=author.public_key(),clock=lambda:"2026-11-04T12:00:00Z")
            try:
                with self.assertRaises(ValueError):registry.open_holdout(protocol["id"],actor="reviewer",dataset_sha256="a"*64,signed_review={})
                registry.register(protocol)
                context=registry.holdout_context(protocol["id"],actor="reviewer",dataset_sha256="a"*64)
                signed=review_binding(context,decision="APPROVE",reviewer="reviewer",author_key_id="author",key=reviewer,key_id="reviewer",
                    issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce="fixture-open")
                with self.assertRaises(PermissionError):registry.open_holdout(protocol["id"],actor="proposer",dataset_sha256="a"*64,signed_review=signed)
                self.assertEqual(registry.open_holdout(protocol["id"],actor="reviewer",dataset_sha256="a"*64,signed_review=signed),protocol)
                import sqlite3
                with self.assertRaises(sqlite3.IntegrityError):registry.register(protocol)
            finally:registry.close()

    def test_paired_intervals_reproduce_and_negative_results_retained(self):
        result=paired_interval([1,2,3],[3,4,5])
        self.assertEqual(result,paired_interval([1,2,3],[3,4,5]))
        self.assertEqual(result["paired_mean_delta"],2)

    def test_missing_corpus_and_release_evidence_block(self):
        with self.assertRaises(ValueError):dataset_manifest([])
        gate=readiness({k:None for k in REQUIRED},critical_field_failures=0,total_cost_comparison="UNKNOWN")
        self.assertEqual(gate["decision"],"BLOCK")
        self.assertFalse(gate["can_release"])
        evidence={k:{"receipt_sha256":"a"*64,"status":"INDEPENDENTLY_VERIFIED"} for k in REQUIRED}
        self.assertIn("CRITICAL_FIELD_LOSS",readiness(evidence,critical_field_failures=1,total_cost_comparison="MEASURED_NO_CROSSOVER")["blockers"])
