"""Studio source custody: adversarial tests for signed mappings and bytes."""
import copy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
import shutil
import subprocess
import sys
import contextlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio_custody import (
    SCHEMA, CustodyError, sign_customer_manifest, verify_customer_manifest, main
)
from signed_bundles import SignatureError
from qualityrag import evaluate
from qualityrag.verify_receipt import _hash, verify_package

def tok(prefix, i):
    return prefix+'_'+f'{i:032x}'

def row(i, origin):
    return {
        "id":tok("ev",i),"requirement_id":"independent",
        "origin":tok("org",origin),"source_ref":tok("src",i),
        "status":"SUPPORTS",
        "observed_at":(datetime.now(timezone.utc)-timedelta(seconds=8)).isoformat().replace("+00:00","Z")
    }

def receipt(evidence):
    pack={"id":"policy","version":"1","requirements":[{"id":"independent","min_independent_sources":2}]}
    at=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    payload={
        "schema":"qualityrag.evidence-replay/v1",
        "evaluationId":"11111111-1111-4111-8111-111111111111",
        "serviceId":"claims-api","environment":"dev",
        "requestId":"request-1","traceId":"trace-1","asOf":at,
        "evaluator":"qualityrag.registry-metadata-gate/v1",
        "policy":pack,"policySha256":_hash(pack),"evidence":evidence,
        "expectedResult":evaluate(pack,evidence,as_of=at),
        "sourceOriginStatus":"CALLER_DECLARED_NOT_AUTHENTICATED",
        "ledgerRecordHash":"f"*64
    }
    return {"payload":payload,"integrity":{
        "sha256":_hash(payload),"externallyAnchored":False,
        "digitallySigned":False,"authenticityVerified":False}}

class CustodyVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.key=Ed25519PrivateKey.generate()
        self.sources={tok("src",1):str(self.root/"a.bin"),tok("src",2):str(self.root/"b.bin")}
        (self.root/"a.bin").write_bytes(b"Exact original policy one\n")
        (self.root/"b.bin").write_bytes(b"Exact original policy two\n")
        self.evidence=[row(1,1),row(2,1)]
        self.receipt=receipt(self.evidence)
        self.manifest=self.build_manifest()

    def build_manifest(self):
        p=self.receipt["payload"]
        return {
            "schema":SCHEMA,"evaluationId":p["evaluationId"],
            "serviceId":p["serviceId"],"environment":p["environment"],
            "policySha256":p["policySha256"],
            "sources":[
                {"source_ref":tok("src",i),"declared_origin":tok("org",1),
                 "content_sha256":sha256(Path(self.sources[tok("src",i)]).read_bytes()).hexdigest(),
                 "content_length":Path(self.sources[tok("src",i)]).stat().st_size}
                for i in (1,2)
            ]
        }

    def sign(self):
        return sign_customer_manifest(
            receipt=self.receipt, manifest=self.manifest,
            source_files=self.sources,private_key=self.key,
            key_id="customer-custodian",nonce="signed-demo-1")

    def verify(self, signed, package=None):
        return verify_customer_manifest(
            receipt=self.receipt if package is None else package,
            signed_custody=signed,public_key=self.key.public_key(),
            source_files=self.sources)

    def test_customer_signed_manifest_exact_bytes(self):
        signed=self.sign()
        result=self.verify(signed)
        self.assertTrue(result["metadataReplayVerified"])
        self.assertTrue(result["sourceCustodyVerified"])
        self.assertEqual(result["custodySourceCount"],2)
        self.assertFalse(result["sourcePublisherAuthenticated"])
        self.assertFalse(result["sourceIndependenceProven"])
        self.assertFalse(result["signatureReplayProtection"])

    def test_forged_independent_source_passes_plain_replay_but_fails_custody(self):
        signed=self.sign()
        attacker=copy.deepcopy(self.receipt)
        attacker["payload"]["evidence"][1]["origin"]=tok("org",2)
        pack=attacker["payload"]["policy"]
        inputs=attacker["payload"]["evidence"]
        attacker["payload"]["expectedResult"]=evaluate(
            pack,inputs,as_of=attacker["payload"]["asOf"])
        attacker["integrity"]["sha256"]=_hash(attacker["payload"])
        self.assertTrue(verify_package(attacker)["verified"])
        self.assertEqual(verify_package(attacker)["verdict"],"ADMIT")
        with self.assertRaisesRegex(CustodyError,"DECLARED_ORIGIN_MISMATCH"):
            self.verify(signed,attacker)

    def test_changed_source_bytes_fail_even_with_correct_attestation(self):
        signed=self.sign()
        (self.root/"b.bin").write_bytes(b"Substituted document\n")
        with self.assertRaisesRegex(CustodyError,"SOURCE_CONTENT_DIGEST_MISMATCH"):
            self.verify(signed)

    def test_unsigned_relabel_cannot_be_repaired_by_new_manifest(self):
        signed=self.sign()
        renamed=copy.deepcopy(self.manifest)
        renamed["sources"][1]["declared_origin"]=tok("org",2)
        # The custodian has not signed this altered manifest.
        tampered=copy.deepcopy(signed)
        tampered["payload"]["observations"]["studio_custody"]=renamed
        with self.assertRaisesRegex(CustodyError,"DECLARED_ORIGIN_MISMATCH"):
            self.verify(tampered)

    def test_signature_substitution_or_untrusted_key_rejected(self):
        signed=self.sign()
        other=Ed25519PrivateKey.generate()
        with self.assertRaises(SignatureError):
            verify_customer_manifest(receipt=self.receipt,signed_custody=signed,
                public_key=other.public_key(),source_files=self.sources)
        altered=copy.deepcopy(signed)
        altered["signature"]="a"*86
        with self.assertRaises((SignatureError,ValueError)):
            self.verify(altered)

    def test_signed_claim_cannot_be_used_for_unrelated_evaluation(self):
        signed=self.sign()
        package=copy.deepcopy(self.receipt)
        package["payload"]["evaluationId"]="22222222-2222-4222-8222-222222222222"
        package["integrity"]["sha256"]=_hash(package["payload"])
        with self.assertRaisesRegex(CustodyError,"CUSTODY_RECEIPT_BINDING_MISMATCH"):
            self.verify(signed,package)

    def test_missing_custody_source_or_bytes_rejected(self):
        signed=self.sign()
        with self.assertRaisesRegex(CustodyError,"MISSING_EXACT_SOURCE_BYTES"):
            verify_customer_manifest(receipt=self.receipt,signed_custody=signed,
                public_key=self.key.public_key(),
                source_files={tok("src",1):self.sources[tok("src",1)]})
        missing=copy.deepcopy(self.manifest)
        missing["sources"]=missing["sources"][:1]
        with self.assertRaisesRegex(CustodyError,"MISSING_OR_UNRELATED_CUSTODY_SOURCE"):
            sign_customer_manifest(receipt=self.receipt,manifest=missing,
                source_files=self.sources,private_key=self.key,
                key_id="customer-custodian",nonce="n")

    def test_identical_bytes_cannot_justify_two_declared_origins(self):
        package=receipt([row(1,1),row(2,2)])
        manifest=copy.deepcopy(self.manifest)
        manifest["sources"][1]["declared_origin"]=tok("org",2)
        (self.root/"b.bin").write_bytes((self.root/"a.bin").read_bytes())
        manifest["sources"][1]["content_sha256"]=manifest["sources"][0]["content_sha256"]
        manifest["sources"][1]["content_length"]=manifest["sources"][0]["content_length"]
        with self.assertRaisesRegex(CustodyError,"IDENTICAL_BYTES_CLAIM_DIFFERENT_ORIGINS"):
            sign_customer_manifest(receipt=package,manifest=manifest,
                source_files=self.sources,private_key=self.key,
                key_id="customer-custodian",nonce="n")

    def test_show_me_forged_origin_demo_against_real_registry_export(self):
        if not shutil.which("node"):
            self.skipTest("Node.js unavailable; cross-runtime demonstration not executed")
        project=Path(__file__).resolve().parents[3]
        result=subprocess.run(
            [sys.executable,str(project/"scripts"/"evidence-custody-show-me.py")],
            cwd=project,text=True,capture_output=True,timeout=40
        )
        self.assertEqual(result.returncode,0,result.stdout+"\\n"+result.stderr)
        output=json.loads(result.stdout)
        self.assertTrue(output["unmodifiedReceipt"]["custodySignatureAndBytesVerified"])
        self.assertEqual(output["forgedOriginReceipt"]["unsignedReplay"],"ADMIT")
        self.assertFalse(output["forgedOriginReceipt"]["customerCustodyAccepted"])
        self.assertEqual(output["forgedOriginReceipt"]["rejectionReason"],
                         "DECLARED_ORIGIN_MISMATCH")

    def test_sign_and_verify_cli_without_exposing_private_key(self):
        from cryptography.hazmat.primitives import serialization
        private=self.root/"custodian-private.pem"
        public=self.root/"custodian-public.pem"
        private.write_bytes(self.key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        private.chmod(0o600)
        public.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo))
        receipt_path=self.root/"receipt.json"
        receipt_path.write_text(json.dumps(self.receipt))
        manifest_path=self.root/"manifest.json"
        manifest_path.write_text(json.dumps(self.manifest))
        signed_path=self.root/"signed.json"
        mappings=[x+"="+y for x,y in self.sources.items()]
        sign_argv=["sign","--receipt",str(receipt_path),"--manifest",str(manifest_path),
            "--private-key",str(private),"--key-id","customer-custodian","--nonce","n1",
            "--out",str(signed_path)]
        for x in mappings:sign_argv+=["--source",x]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(sign_argv),0)
        verify_argv=["verify","--receipt",str(receipt_path),
            "--attestation",str(signed_path),"--public-key",str(public)]
        for x in mappings:verify_argv+=["--source",x]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(verify_argv),0)
        self.assertIn('"sourceCustodyVerified": true',out.getvalue())
        self.assertTrue(signed_path.is_file())

if __name__ == "__main__":
    unittest.main()
