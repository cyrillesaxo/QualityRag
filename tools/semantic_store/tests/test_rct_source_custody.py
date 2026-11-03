"""v1.9 signed primary-source custody verification regression suite."""
import tempfile
import sys
import unittest
from hashlib import sha256
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packspec_compiler"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_policy, sign_attestation, SignatureError
from signed_gate import SQLiteNonceStore
from rct_lens import compile_lens
from rct_packspec_bridge import bind_candidate
from rct_witness_bridge import make_mapping
from rct_source_custody import assess_source_custody
from test_rct_signed_lineage import constraint_ir, witness, START, END, NOW
from store import digest


class SourceCustodyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.nonces=SQLiteNonceStore(Path(temp.name)/"custody-nonces.db")
        self.ir=constraint_ir()
        self.lens=compile_lens("The heart is located in the thorax.",
                               lens_id="heart",purpose="study",
                               required=("heart-location",),
                               permitted_omissions=("occlusion",))
        self.pack={"id":"study","version":"1","requirements":[
            {"id":"heart-evidence","min_independent_sources":2},
            {"id":"occlusion-evidence","min_independent_sources":1}]}
        self.mapping=make_mapping(self.lens,pack=self.pack,predicate_requirements={
            "heart-location":"heart-evidence","occlusion":"occlusion-evidence"})
        self.binding=bind_candidate(self.lens,self.ir,purpose="study")
        self.policy_key=Ed25519PrivateKey.generate()
        self.evidence_key=Ed25519PrivateKey.generate()
        self.custodian_key=Ed25519PrivateKey.generate()
        self.policy=sign_policy(self.ir,self.policy_key,key_id="policy",
             service="example",environment="test",sequence=1,
             issued_at=START,expires_at=END)
        self.records=[
            witness("a","heart-evidence","root-A"),
            witness("b","heart-evidence","derived-B",parents=("a",)),
            witness("c","occlusion-evidence","root-C")]
        self.source_bytes={"root-A":b"primary document A",
                           "root-C":b"another primary document C"}
        self.observations={"rct_binding":{
            "lens_fingerprint":self.lens["fingerprint"],
            "source_sha256":self.lens["source_sha256"],
            "evidence_pack_sha256":digest(self.pack),
            "witness_mapping_sha256":self.mapping["fingerprint"]}}
        self.counter=0

    def manifests(self,source_bytes=None):
        data=self.source_bytes if source_bytes is None else source_bytes
        roots={"root-A":"source#a","root-C":"source#c"}
        return [{"root_id":root,"source_ref":ref,
                 "content_sha256":sha256(data[root]).hexdigest(),
                 "content_length":len(data[root])}
                for root,ref in roots.items()]

    def _signed(self,records=None,manifest=None):
        self.counter+=1
        key=str(self.counter)
        data=self.records if records is None else records
        custody=self.manifests() if manifest is None else manifest
        observations_sig=sign_attestation(
            data,self.observations,self.evidence_key,key_id="evidence",
            policy_signature=self.policy["signature"],
            service="example",environment="test",nonce="evidence-"+key,
            issued_at=START,expires_at=END)
        custody_sig=sign_attestation(
            [],{"custody_roots":custody},self.custodian_key,key_id="custodian",
            policy_signature=self.policy["signature"],
            service="example",environment="test",nonce="custody-"+key,
            issued_at=START,expires_at=END)
        return observations_sig,custody_sig

    def assess(self, records=None, source_bytes=None, manifest=None, **options):
        data=self.records if records is None else records
        signed,signed_custody=self._signed(records=data,manifest=manifest)
        arguments=dict(
            lens=self.lens,reviewed_ir=self.ir,ir_binding=self.binding,
            evidence_pack=self.pack,witness_mapping=self.mapping,
            signed_policy=self.policy,signed_observations=signed,
            signed_custody=signed_custody,
            policy_keys={"policy":self.policy_key.public_key()},
            attestor_keys={"evidence":self.evidence_key.public_key()},
            custodian_keys={"custodian":self.custodian_key.public_key()},
            service="example",environment="test",minimum_sequence=1,
            nonce_accepted=self.nonces,witnesses=data,
            observations=self.observations,as_of=NOW,
            source_bytes=self.source_bytes if source_bytes is None else source_bytes)
        arguments.update(options)
        return assess_source_custody(**arguments)

    def test_custodian_signs_matching_source_bytes(self):
        r=self.assess()
        self.assertEqual(r["source_custody"]["verified_root_bytes"],2)
        self.assertEqual(r["source_custody"]["custody_assurance"],
                         "SIGNED_HASH_MATCHES_SUPPLIED_BYTES_ONLY")
        self.assertEqual(r["qualityrag_admission"],"INCONCLUSIVE")
        self.assertFalse(r["can_generate"])
        self.assertEqual(r["verdict"],"INCONCLUSIVE")

    def test_byte_substitution_rejected_even_with_unchanged_signed_manifest(self):
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            self.assess(source_bytes={"root-A":b"changed", "root-C":self.source_bytes["root-C"]})

    def test_manifest_missing_primary_source_rejected(self):
        with self.assertRaisesRegex(ValueError,"Unattested primary root"):
            self.assess(manifest=self.manifests()[:1])

    def test_identical_bytes_are_marked_as_correlated_roots(self):
        same=b"one cached article"
        both={"root-A":same,"root-C":same}
        result=self.assess(source_bytes=both,manifest=self.manifests(both))
        self.assertEqual(result["source_custody"]["identical_content_root_groups"],
                         [["root-A","root-C"]])
        self.assertIn("IDENTICAL_CONTENT_ROOTS",result["blockers"])

    def test_mismatched_reference_rejected(self):
        altered=self.manifests()
        altered[0]["source_ref"]="incorrect#ref"
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            self.assess(manifest=altered)

    def test_untrusted_custodian_rejected(self):
        with self.assertRaises(SignatureError):
            self.assess(custodian_keys={})

    def test_shared_custodian_evidence_key_id_rejected(self):
        with self.assertRaisesRegex(ValueError,"separate"):
            self.assess(custodian_keys={"evidence":self.custodian_key.public_key()})

    def test_replay_of_same_custody_attestation_rejected(self):
        signed,custody=self._signed()
        params=dict(
            signed_observations=signed,signed_custody=custody)
        self.assess(**params)
        with self.assertRaises(SignatureError):
            self.assess(**params)

    def test_missing_ancestor_still_fails_closed(self):
        wrong=[witness("a","heart-evidence","root-A",parents=("missing",)),
               witness("c","occlusion-evidence","root-C")]
        with self.assertRaises(ValueError):
            self.assess(records=wrong)

    def test_contradiction_remains_refusal(self):
        altered=[dict(self.records[0]),dict(self.records[1]),dict(self.records[2])]
        altered[2]["status"]="CONTRADICTS"
        result=self.assess(records=altered)
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertFalse(result["can_generate"])


if __name__=="__main__":
    unittest.main()
