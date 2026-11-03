"""v1.8 signed lineage: exact signed records, ancestry collapse, replay and safety."""
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packspec_compiler"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typed_ir import _fingerprint
from signed_bundles import sign_policy, sign_attestation, SignatureError
from signed_gate import SQLiteNonceStore

from rct_lens import compile_lens
from rct_packspec_bridge import bind_candidate
from rct_witness_bridge import make_mapping
from rct_signed_lineage import assess_signed_lineage, _lineage
from store import digest

START = "2026-11-03T17:00:00Z"
NOW = "2026-11-03T18:00:00Z"
END = "2026-11-04T17:00:00Z"


def constraint_ir():
    source = "a" * 64
    nodes = [{"node_id":"heart","kind":"EVIDENCE_PRESENCE",
              "runtime":"METADATA_GATE_V0_1","status":"PROJECTION_ONLY",
              "parameters":{"requirement_id":"heart-evidence","min_independent_sources":1},
              "source":{"source_sha256":source},
              "review":{"approved":True}}]
    return {"schema":"qualityrag.constraint-ir/v1", "source":{"sha256":source},
            "nodes":nodes,
            "summary":{"total":1,"evidence_presence_projections":1,
                       "deferred_semantic_constraints":0},
            "ir_sha256":_fingerprint({"source_sha256":source,"nodes":nodes})}


def witness(wid, requirement, origin, parents=(), status="SUPPORTS"):
    return {"id":wid, "requirement_id":requirement,"origin":origin,
            "derives_from":list(parents), "source_ref":"source#"+wid,
            "observed_at":START,"status":status}


class SignedLineageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = SQLiteNonceStore(Path(self.temp.name) / "lineage-nonces.db")
        self.ir = constraint_ir()
        self.lens = compile_lens(
            "The heart is located in the thorax.",lens_id="heart",
            purpose="study",required=("heart-location",),
            permitted_omissions=("occlusion",))
        self.pack = {"id":"study","version":"1","requirements":[
            {"id":"heart-evidence","min_independent_sources":2},
            {"id":"occlusion-evidence","min_independent_sources":1},
        ]}
        self.mapping = make_mapping(
            self.lens,pack=self.pack,predicate_requirements={
                "heart-location":"heart-evidence",
                "occlusion":"occlusion-evidence"})
        self.ir_binding = bind_candidate(self.lens,self.ir,purpose="study")
        self.policy_private = Ed25519PrivateKey.generate()
        self.attestor_private = Ed25519PrivateKey.generate()
        self.policy = sign_policy(
            self.ir,self.policy_private,key_id="policy-v1",
            service="demo",environment="test",sequence=1,
            issued_at=START,expires_at=END)
        self.observations = {"rct_binding":{
            "lens_fingerprint":self.lens["fingerprint"],
            "source_sha256":self.lens["source_sha256"],
            "evidence_pack_sha256":digest(self.pack),
            "witness_mapping_sha256":self.mapping["fingerprint"]}}
        self.witnesses = [
            witness("a","heart-evidence","root-A"),
            witness("b","heart-evidence","claimed-B",parents=("a",)),
            witness("c","occlusion-evidence","root-C")]
        self.nonce=0

    def assess(self, records=None, **kwargs):
        records=self.witnesses if records is None else records
        self.nonce += 1
        attestation=sign_attestation(
            records,self.observations,self.attestor_private,
            key_id="attestor-v1",policy_signature=self.policy["signature"],
            service="demo",environment="test",nonce="test-"+str(self.nonce),
            issued_at=START,expires_at=END)
        options={
            "lens":self.lens,"reviewed_ir":self.ir,"ir_binding":self.ir_binding,
            "evidence_pack":self.pack,"witness_mapping":self.mapping,
            "signed_policy":self.policy,"signed_observations":attestation,
            "policy_keys":{"policy-v1":self.policy_private.public_key()},
            "attestor_keys":{"attestor-v1":self.attestor_private.public_key()},
            "service":"demo","environment":"test","minimum_sequence":1,
            "nonce_accepted":self.ledger,"witnesses":records,
            "observations":self.observations,"as_of":NOW}
        options.update(kwargs)
        return assess_signed_lineage(**options)

    def test_signed_derivation_shares_same_root(self):
        result=self.assess()
        self.assertTrue(result["verified_record_signature"])
        self.assertEqual(result["lineage"]["witness_roots"]["b"],["root-A"])
        self.assertEqual(result["declared_component_coverage"]["heart-evidence"]
                         ["declared_lineage_component_count"],1)
        self.assertEqual(result["declared_component_coverage"]["heart-evidence"]
                         ["missing_components"],1)
        self.assertIn("SHARED_ANCESTOR_DEPENDENCY",result["blockers"])
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertFalse(result["can_generate"])

    def test_distinct_declared_roots_still_not_proven_independent(self):
        records=[witness("a","heart-evidence","root-A"),
                 witness("b","heart-evidence","root-B"),
                 witness("c","occlusion-evidence","root-C")]
        result=self.assess(records)
        self.assertEqual(result["declared_component_coverage"]["heart-evidence"]
                         ["declared_lineage_component_count"],2)
        self.assertEqual(result["declared_component_coverage"]["heart-evidence"]
                         ["proven_independence"],"UNKNOWN")
        self.assertEqual(result["verdict"],"INCONCLUSIVE")

    def test_missing_ancestor_and_cycle_rejected(self):
        with self.assertRaisesRegex(ValueError,"Unresolved witness ancestor"):
            self.assess([witness("a","heart-evidence","A",parents=("missing",)),
                         witness("b","occlusion-evidence","B")])
        with self.assertRaisesRegex(ValueError,"Cycle"):
            self.assess([witness("a","heart-evidence","A",parents=("b",)),
                         witness("b","heart-evidence","B",parents=("a",)),
                         witness("c","occlusion-evidence","C")])

    def test_wrong_signed_binding_rejected(self):
        changed={**self.observations, "rct_binding":dict(
            self.observations["rct_binding"], source_sha256="0"*64)}
        with self.assertRaisesRegex(ValueError,"bind exact RCT lens"):
            self.assess(observations=changed)

    def test_tampered_attested_witness_rejected(self):
        records=list(self.witnesses)
        self.nonce+=1
        signed=sign_attestation(
            records,self.observations,self.attestor_private,
            key_id="attestor-v1",policy_signature=self.policy["signature"],
            service="demo",environment="test",nonce="tamper-1",
            issued_at=START,expires_at=END)
        forged=[dict(row) for row in records]
        forged[1]["derives_from"]=[]
        with self.assertRaises(SignatureError):
            self.assess(forged,signed_observations=signed)

    def test_signed_attestation_replay_fails(self):
        records=list(self.witnesses)
        self.nonce+=1
        signed=sign_attestation(
            records,self.observations,self.attestor_private,
            key_id="attestor-v1",policy_signature=self.policy["signature"],
            service="demo",environment="test",nonce="replay-1",
            issued_at=START,expires_at=END)
        first=self.assess(records,signed_observations=signed)
        self.assertEqual(first["verdict"],"INCONCLUSIVE")
        with self.assertRaises(SignatureError):
            self.assess(records,signed_observations=signed)

    def test_explicit_contradiction_preserved(self):
        records=[witness("a","heart-evidence","A"),
                 witness("b","heart-evidence","B"),
                 witness("c","occlusion-evidence","C",status="CONTRADICTS")]
        result=self.assess(records)
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertFalse(result["can_generate"])

    def test_unverified_primary_sources_not_claimed_authenticated(self):
        result=self.assess()
        self.assertEqual(result["lineage"]["lineage_provenance"],
                         "SIGNED_RECORDS_NOT_AUTHENTICATED_PRIMARY_SOURCES")
        self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
