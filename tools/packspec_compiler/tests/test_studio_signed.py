import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from compiler import inspect
from typed_ir import compile_ir
from signed_bundles import verify_policy, SignatureError
from studio_sign import sign_from_file
from studio_signed_client import fetch_signed_policy, SignedStudioError

NOW = "2026-11-02T10:05:00Z"

class FakeResponse:
    status=200
    def __init__(self, payload): self.payload=payload
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,max_size): return self.payload[:max_size]

class FakeOpener:
    def __init__(self,response): self.response=response
    def open(self, req, timeout):
        assert req.full_url=="http://127.0.0.1:5055/v1/signed/resolve/study/dev"
        assert req.get_header("Authorization")=="Bearer secret"
        return FakeResponse(self.response)

class SignedStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        file=self.root/"source.json"
        file.write_text(json.dumps({"id":"study","version":"1","rules":[
            {"rule":"A learner assessment must have an evidence record"}]}))
        report=inspect(file)
        candidate=report["candidate_constraints"][0]
        mapping={"schema":"qualityrag.typed-mapping/v1",
            "source_sha256":report["source"]["sha256"],
            "rules":[{"candidate_id":candidate["candidate_id"],"node_id":"record",
                      "kind":"EVIDENCE_PRESENCE",
                      "parameters":{"requirement_id":"assessment-record"},
                      "reviewed_by":"test-reviewer","approved":True,
                      "rationale":"Require direct supporting evidence of the assessment"}]}
        self.ir=compile_ir(report,mapping)
        (self.root/"ir.json").write_text(json.dumps(self.ir))
        self.private=Ed25519PrivateKey.generate()
        pem=self.private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())
        self.key_file=self.root/"governance.pem"
        self.key_file.write_bytes(pem)
        self.key_file.chmod(0o600)
    def signed(self):
        return sign_from_file(ir_file=str(self.root/"ir.json"),
            private_key_pem=str(self.key_file),output_file=str(self.root/"signed.json"),
            key_id="governance-v1",service="study",environment="dev",sequence=4,
            issued_at="2026-11-02T10:00:00Z",expires_at="2026-11-03T10:00:00Z")

    def test_offline_signatures_verify_and_never_overwrite(self):
        bundle=self.signed()
        trust={"governance-v1":self.private.public_key()}
        self.assertEqual(verify_policy(bundle,trust,service="study",environment="dev",
            as_of=NOW,minimum_sequence=4)["sequence"],4)
        with self.assertRaises(FileExistsError):
            self.signed()
        with self.assertRaises(SignatureError):
            verify_policy(bundle,trust,service="other",environment="dev",
                as_of=NOW,minimum_sequence=4)
        self.assertFalse((self.root/"copied-governance.pem").exists())

    def test_private_key_permissions_checked(self):
        if os.name=="posix":
            self.key_file.chmod(0o644)
            with self.assertRaisesRegex(ValueError,"group or others"):
                self.signed()

    def test_signed_resolution_never_downgrades_to_unsigned(self):
        bundle=self.signed()
        envelope={"serviceId":"study","environment":"dev","sequence":4,
                  "status":"PUBLISHED","signedPolicy":bundle}
        url="http://127.0.0.1:5055"
        with patch("studio_signed_client.request.build_opener",return_value=FakeOpener(json.dumps(envelope).encode())):
            self.assertEqual(fetch_signed_policy(url,"secret","study","dev")["signature"],bundle["signature"])
        envelope["signedPolicy"]=None
        with patch("studio_signed_client.request.build_opener",return_value=FakeOpener(json.dumps(envelope).encode())):
            with self.assertRaisesRegex(SignedStudioError,"Missing signed policy"):
                fetch_signed_policy(url,"secret","study","dev")
        envelope["signedPolicy"]=bundle
        envelope["sequence"]=2
        with patch("studio_signed_client.request.build_opener",return_value=FakeOpener(json.dumps(envelope).encode())):
            with self.assertRaisesRegex(SignedStudioError,"sequence mismatch"):
                fetch_signed_policy(url,"secret","study","dev")
        with self.assertRaisesRegex(SignedStudioError,"HTTPS"):
            fetch_signed_policy("http://other.example","secret","study","dev")

if __name__=="__main__":
    unittest.main()
