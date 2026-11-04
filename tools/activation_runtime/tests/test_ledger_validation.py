from pathlib import Path
import sqlite3
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.gardener import ledger
from tools.activation_runtime.ledger_validation import validate_claim,review_context
from tools.activation_runtime.authority import review_binding


class LedgerValidationTests(unittest.TestCase):
    def test_validated_requires_real_signature_bound_to_claim_and_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            db=sqlite3.connect(Path(root)/"ledger.sqlite");ledger.initialize(db)
            self.addCleanup(db.close)
            at="2026-11-04T12:00:00Z"
            ledger.claim(db,claim_id="claim1",project="test",kind="EXPERIMENT",statement="Finite fixture-only result",at=at)
            ledger.evidence(db,evidence_id="review1",kind="REVIEW",uri="https://example.invalid/test-review",description="Authored test reviewer fixture",at=at)
            ledger.evidence(db,evidence_id="test1",kind="TEST_RESULT",uri="https://example.invalid/test-result",description="Authored cryptographic test fixture",at=at)
            with self.assertRaises(ledger.LedgerError):
                ledger.assess(db,event_id="unverified",claim_id="claim1",assessment="VALIDATED",reason="Must refuse",actor="proposer",evidence_ids=["review1","test1"],at=at)
            claim_hash=db.execute("SELECT content_hash FROM research_claims WHERE claim_id='claim1'").fetchone()[0]
            evidence=dict(db.execute("SELECT evidence_id,record_hash FROM research_evidence"))
            context=review_context(db,claim={"claim_id":"claim1","content_hash":claim_hash},
                evidence=[{"evidence_id":eid,"record_hash":h} for eid,h in evidence.items()],
                scope="AUTHORED_TEST_ONLY_NOT_REAL_RESEARCH",tenant="test",ledger_id="fixture-ledger",
                actor="test-reviewer",event_id="verified")
            reviewer=Ed25519PrivateKey.generate();author=Ed25519PrivateKey.generate()
            signed=review_binding(context,decision="APPROVE",reviewer="test-reviewer",author_key_id="author",key=reviewer,key_id="reviewer",
                issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce="review-once")
            result=validate_claim(db,event_id="verified",claim_id="claim1",actor="test-reviewer",evidence_ids=["review1","test1"],
                scope=context["validation_scope"],signed_review=signed,reviewer_keys={"reviewer":reviewer.public_key()},
                author_public_key=author.public_key(),as_of=at,tenant="test",ledger_id="fixture-ledger")
            self.assertEqual(result["assessment"],"VALIDATED")
            self.assertTrue(ledger.verify_integrity(db)["consistent"])
            with self.assertRaises(ledger.LedgerError):
                validate_claim(db,event_id="replay",claim_id="claim1",actor="test-reviewer",evidence_ids=["review1","test1"],
                    scope=context["validation_scope"],signed_review=signed,reviewer_keys={"reviewer":reviewer.public_key()},
                    author_public_key=author.public_key(),as_of=at,tenant="test",ledger_id="fixture-ledger")
