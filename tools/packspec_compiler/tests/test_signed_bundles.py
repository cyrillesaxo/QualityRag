import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from compiler import inspect
from typed_ir import compile_ir
from signed_bundles import (
    SignatureError, canonical, load_canonical_json,
    sign, verify, sign_policy, verify_policy, sign_attestation, verify_attestation,
    POLICY_SCHEMA, ATTEST_SCHEMA,
)
from signed_gate import guarded_generate_signed, SQLiteNonceStore

NOW = "2026-11-02T10:05:00Z"
START = "2026-11-02T10:00:00Z"
END = "2026-11-03T10:00:00Z"


class SignedBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        path = root / "source.json"
        path.write_text(json.dumps({"pack_id":"ops","version":"1","rules":[
            {"rule":"A governing control must have a source witness"},
            {"rule":"Cold retrieval must follow a prior learner attempt"}
        ]}))
        report = inspect(path)
        def approved(item, node_id, kind, params):
            return {"candidate_id":item["candidate_id"],"node_id":node_id,
                    "kind":kind,"parameters":params,"approved":True,
                    "reviewed_by":"domain-reviewer",
                    "rationale":"Review of a narrow control requirement from the source"}
        rules = [
            approved(report["candidate_constraints"][0], "control", "EVIDENCE_PRESENCE",
                     {"requirement_id":"governing-control","min_independent_sources":1}),
            approved(report["candidate_constraints"][1], "ordering", "TEMPORAL",
                     {"relation":"AFTER","anchor":"attempt","subject":"retrieval"}),
        ]
        self.ir = compile_ir(report, {"schema":"qualityrag.typed-mapping/v1",
                                      "source_sha256":report["source"]["sha256"],"rules":rules})
        self.policy_key=Ed25519PrivateKey.generate()
        self.evidence_key=Ed25519PrivateKey.generate()
        self.policy_keys={"policy-v1":self.policy_key.public_key()}
        self.attestor_keys={"worker-v1":self.evidence_key.public_key()}
        self.policy = sign_policy(self.ir,self.policy_key,key_id="policy-v1",
            service="tutor",environment="prod",sequence=12,issued_at=START,expires_at=END)
        self.witnesses=[{"id":"w1","origin":"annex","requirement_id":"governing-control",
                         "source_ref":"annex#187","status":"SUPPORTS","observed_at":START}]
        self.obs={"events":{
           "attempt":{"at":"2026-10-30T10:00:00Z","source_ref":"attempt#1"},
           "retrieval":{"at":START,"source_ref":"retrieval#2"}
        },"probes":{}}
        self.attestation=sign_attestation(self.witnesses,self.obs,self.evidence_key,
            key_id="worker-v1",policy_signature=self.policy["signature"],service="tutor",
            environment="prod",nonce="request-01",issued_at=START,expires_at=END)
        self.store=SQLiteNonceStore(root / "nonce-ledger.sqlite")
        self.calls=0

    def call(self, **kwargs):
        options=dict(signed_policy=self.policy,signed_observations=self.attestation,
            policy_keys=self.policy_keys,attestor_keys=self.attestor_keys,
            service="tutor",environment="prod",minimum_sequence=12,
            nonce_accepted=self.store,witnesses=self.witnesses,
            observations=self.obs,as_of=NOW,
            generator=self.generate)
        options.update(kwargs)
        return guarded_generate_signed(**options)

    def generate(self):
        self.calls+=1
        return "answer"

    def test_signed_valid_policy_and_attestation_generate_once(self):
        result=self.call()
        self.assertTrue(result["generated"])
        self.assertEqual(self.calls,1)
        self.assertEqual(result["decision"]["verdict"],"ADMIT")
        self.assertEqual(result["decision"]["signed_policy"]["sequence"],12)
        self.assertEqual(result["decision"]["attestation_method"],"ED25519_SIGNED_BUNDLE")
        replay=self.call()
        self.assertFalse(replay["generated"])
        self.assertEqual(replay["decision"]["verdict"],"INCONCLUSIVE")
        self.assertEqual(self.calls,1)
        self.assertFalse(SQLiteNonceStore(self.store.path)("tutor","prod","request-01"))

    def test_invalid_policy_signature_and_modified_ir_block(self):
        for change in ("tampered","wrong-pubkey","wrong-service","rollback","expired"):
            options={}
            if change=="tampered":
                policy=json.loads(json.dumps(self.policy))
                policy["payload"]["ir"]["nodes"][0]["parameters"]["requirement_id"]="other"
                options["signed_policy"]=policy
            if change=="wrong-pubkey":
                options["policy_keys"]={"policy-v1":Ed25519PrivateKey.generate().public_key()}
            if change=="wrong-service":options["service"]="other"
            if change=="rollback":options["minimum_sequence"]=13
            if change=="expired":options["as_of"]="2026-11-04T10:00:00Z"
            with self.subTest(change=change):
                with self.assertRaises(SignatureError):
                    self.call(**options)
                self.assertEqual(self.calls,0)

    def test_invalid_attestation_blocks_and_preserves_nonce(self):
        for change in ("changed-witness","changed-probe","other-key","wrong-policy","expired"):
            options={}
            if change=="changed-witness":
                records=json.loads(json.dumps(self.witnesses))
                records[0]["source_ref"]="fake#1"
                options["witnesses"]=records
            if change=="changed-probe":
                options["observations"]={**self.obs,"probes":{"bogus":True}}
            if change=="other-key":options["attestor_keys"]={"worker-v1":Ed25519PrivateKey.generate().public_key()}
            if change=="wrong-policy":
                att=json.loads(json.dumps(self.attestation))
                att["payload"]["policy_signature"]="wrong"
                options["signed_observations"]=att
            if change=="expired":
                att=sign_attestation(self.witnesses,self.obs,self.evidence_key,
                   key_id="worker-v1",policy_signature=self.policy["signature"],service="tutor",
                   environment="prod",nonce="request-01",
                   issued_at="2026-11-01T10:00:00Z",expires_at="2026-11-02T10:01:00Z")
                options["signed_observations"]=att
            with self.subTest(change=change):
                result=self.call(**options)
                self.assertFalse(result["generated"])
                self.assertEqual(result["decision"]["verdict"],"INCONCLUSIVE")
                self.assertEqual(self.calls,0)
        self.assertTrue(self.store("tutor","prod","request-01"))

    def test_invalid_evidence_and_semantic_check_do_not_consume_nonce(self):
        missing=self.call(witnesses=[])
        self.assertFalse(missing["generated"])
        self.assertEqual(missing["decision"]["evidence"]["verdict"],"INCONCLUSIVE")
        invalid=json.loads(json.dumps(self.obs))
        invalid["events"]["retrieval"]["at"]="2026-10-29T10:00:00Z"
        result=self.call(observations=invalid)
        self.assertEqual(result["decision"]["semantics"]["verdict"],"REFUSE")
        self.assertFalse(result["generated"])
        self.assertTrue(self.store("tutor","prod","request-01"))

    def test_unknown_keys_and_role_separation(self):
        with self.assertRaisesRegex(SignatureError,"Unknown"):
            verify_policy(self.policy,{},service="tutor",environment="prod",
                          as_of=NOW,minimum_sequence=12)
        # A policy signing key is not automatically trusted to attest observations.
        wrong=sign_attestation(self.witnesses,self.obs,self.policy_key,key_id="policy-v1",
             policy_signature=self.policy["signature"],service="tutor",environment="prod",
             nonce="request-02",issued_at=START,expires_at=END)
        result=self.call(signed_observations=wrong)
        self.assertFalse(result["generated"])
        self.assertEqual(self.calls,0)

    def test_key_rotation_uses_explicit_trust_store(self):
        rotated=Ed25519PrivateKey.generate()
        new_policy=sign_policy(self.ir,rotated,key_id="policy-v2",service="tutor",environment="prod",
                               sequence=13,issued_at=START,expires_at=END)
        with self.assertRaises(SignatureError):
            verify_policy(new_policy,self.policy_keys,service="tutor",environment="prod",
                          as_of=NOW,minimum_sequence=13)
        trusted={**self.policy_keys,"policy-v2":rotated.public_key()}
        self.assertEqual(verify_policy(new_policy,trusted,service="tutor",
                         environment="prod",as_of=NOW,minimum_sequence=13)["sequence"],13)

    def test_canonicalization_and_cross_domain_attack(self):
        doc={"z":[1,True,None],"a":"é"}
        self.assertEqual(canonical(doc),canonical({"a":"é","z":[1,True,None]}))
        self.assertEqual(load_canonical_json(canonical(doc)),doc)
        for blob in (b'{"a":1,"a":2}',b'{"a": 1}',b'{"a":1.0}',b'{"a":NaN}'):
            with self.subTest(blob=blob):
                with self.assertRaises(SignatureError):
                    load_canonical_json(blob)
        with self.assertRaises(SignatureError):
            canonical({"numeric":1.2})
        with self.assertRaises(SignatureError):
            verify(self.policy,self.policy_keys,schema=ATTEST_SCHEMA)

    def test_nonce_store_is_durable_and_rejects_duplicates(self):
        ledger=SQLiteNonceStore(Path(self.tmp.name)/"shared-ledger.db")
        self.assertTrue(ledger("tutor","prod","nonce-1"))
        self.assertFalse(SQLiteNonceStore(ledger.path)("tutor","prod","nonce-1"))
        self.assertTrue(SQLiteNonceStore(ledger.path)("other","prod","nonce-1"))
        with self.assertRaises(ValueError):
            SQLiteNonceStore(":memory:")

if __name__ == "__main__":
    unittest.main()
