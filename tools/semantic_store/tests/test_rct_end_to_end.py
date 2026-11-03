"""End-to-end candidate pipeline, adversarial conservation and signed custody.

These tests exercise the complete *research* path, not APX production parity.
"""
import tempfile
import sys
import unittest
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packspec_compiler"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from signed_bundles import sign_attestation, sign_policy
from signed_gate import SQLiteNonceStore
from rct_end_to_end import run_structural_pipeline, attach_signed_governance
from rct_conservation import audit_finite_conservation
from rct_reference_frame import encode_reference_frame, decode_reference_frame
from rct_assurance_candidates import structural_drift_candidate, bounded_repair_candidates
from rct_packspec_bridge import bind_candidate
from rct_witness_bridge import make_mapping
from store import digest
from test_rct_purpose_lens import fixture, grammar
from test_rct_signed_lineage import constraint_ir, START, NOW, END


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.train, self.train_labels = fixture("train-")
        self.source, self.labels = fixture("held-")
        self.spec = grammar()

    def pipeline(self, **kwargs):
        params = dict(
            training=self.train, training_labels=self.train_labels,
            source=self.source, labels=self.labels, grammar=self.spec,
            purpose="classification-training", lens_id="full-path",
            required_predicates=["p","q","r"],
            allowed_omission_predicates=["context"])
        params.update(kwargs)
        return run_structural_pipeline(**params)

    def test_all_stages_and_exact_reconstruction(self):
        run = self.pipeline()
        self.assertEqual(run["status"], "STRUCTURAL_CHECKS_PASS")
        self.assertEqual(run["conservation"]["finite_structural_verdict"], "SAT")
        self.assertTrue(run["reconstruction"]["exact_canonical_round_trip"])
        self.assertFalse(run["reconstruction"]["native_ff_rct"])
        self.assertEqual(run["source_sha256"], run["reconstruction"]["source_sha256"])
        self.assertEqual(decode_reference_frame(run["reconstruction"]["frame"]),
                         self.source)
        self.assertEqual(len(run["purpose_lens"]["omitted_fact_ids"]), 4)
        self.assertEqual(run["witness_cover"]["minimality"], "NOT_PROVEN")
        self.assertFalse(run["can_generate"])
        self.assertEqual(run["qualityrag_admission"], "INCONCLUSIVE")

    def test_source_tampering_and_incorrect_omission_detected(self):
        run=self.pipeline()
        mutated=dict(run["purpose_lens"])
        mutated["omitted_fact_ids"] += [mutated["protected_fact_ids"][0]]
        with self.assertRaises(ValueError):
            audit_finite_conservation(self.source, mutated)
        frame=dict(run["reconstruction"]["frame"])
        frame["source_sha256"]="0"*64
        with self.assertRaises(ValueError):
            decode_reference_frame(frame)

    def test_wrong_source_fingerprint_rejected(self):
        run=self.pipeline()
        changed=dict(self.source, facts=[dict(f) for f in self.source["facts"]])
        changed["facts"].append({
            "id":"unseen","subject":"held-new","predicate":"context",
            "object":"held-noise","source_ref":"ref#new"})
        with self.assertRaises(ValueError):
            audit_finite_conservation(changed, run["purpose_lens"])
        drift=structural_drift_candidate(self.source,changed)
        self.assertTrue(drift["requires_revalidation"])
        self.assertEqual(drift["added_fact_ids"],["unseen"])
        self.assertEqual(drift["semantic_drift"],"UNKNOWN")

    def test_structural_holdout_counterexample_blocks_pipeline(self):
        changed=dict(self.source, facts=[dict(f) for f in self.source["facts"]])
        changed["facts"].append({
            "id":"adversarial-r","subject":"held-negative-path",
            "predicate":"r","object":"held-answer-n","source_ref":"ref#adversarial"})
        run=self.pipeline(source=changed)
        self.assertEqual(run["stage"],"HELDOUT_VALIDATION")
        self.assertEqual(run["status"],"COUNTEREXAMPLE")
        self.assertFalse(run["can_generate"])

    def test_reference_frame_detects_index_tampering_and_has_bounded_size(self):
        f=encode_reference_frame(self.source, level=9)
        self.assertGreater(f["compressed_bytes"],0)
        self.assertEqual(decode_reference_frame(f),self.source)
        bad=dict(f)
        bad["levels"]=dict(f["levels"],L0={"fact_count":0})
        with self.assertRaises(ValueError):
            decode_reference_frame(bad)

    def test_bounded_repairs_never_execute(self):
        r=bounded_repair_candidates({
            "witness_coverage":{"wgap":[{
                "requirement_id":"evidence","missing_sources":2}]},
            "blockers":["OMISSION_SAFETY_NOT_ESTABLISHED"]})
        self.assertEqual(len(r["actions"]),2)
        self.assertEqual(r["actions"][0]["minimum_additional_declared_sources"],2)
        self.assertFalse(r["automatic_execution"])
        self.assertEqual(r["semantic_recovery"],"NOT_VERIFIED")

    def test_signed_end_to_end_receipt_never_admits(self):
        structural=self.pipeline()
        lens=structural["purpose_lens"]
        ir=constraint_ir()
        # The existing test IR uses heart-evidence; the generated RCT lens
        # lists p, q, r and context, so the witness pack maps all distinctions.
        pack={"id":"end-to-end","version":"1","requirements":[
            {"id":"p-evidence","min_independent_sources":1},
            {"id":"q-evidence","min_independent_sources":1},
            {"id":"r-evidence","min_independent_sources":1},
            {"id":"context-evidence","min_independent_sources":1},
            {"id":"heart-evidence","min_independent_sources":1},
        ]}
        map_=make_mapping(lens,pack=pack,predicate_requirements={
            "p":"p-evidence", "q":"q-evidence",
            "r":"r-evidence", "context":"context-evidence"})
        bound=bind_candidate(lens,ir,purpose=lens["purpose"])
        roots=["p","q","r","context","heart"]
        witnesses=[
            {"id":x,"origin":x+"-root","requirement_id":x+"-evidence",
             "derives_from":[],"source_ref":"primary#"+x,
             "observed_at":START,"status":"SUPPORTS"}
            for x in roots]
        blobs={x+"-root":("primary data for "+x).encode() for x in roots}
        custody_manifest=[
            {"root_id":x+"-root","source_ref":"primary#"+x,
             "content_sha256":sha256(blobs[x+"-root"]).hexdigest(),
             "content_length":len(blobs[x+"-root"])}
            for x in roots]
        observations={"rct_binding":{
            "lens_fingerprint":lens["fingerprint"],
            "source_sha256":lens["source_sha256"],
            "evidence_pack_sha256":digest(pack),
            "witness_mapping_sha256":map_["fingerprint"]}}
        policy_key=Ed25519PrivateKey.generate()
        evidence_key=Ed25519PrivateKey.generate()
        custodian_key=Ed25519PrivateKey.generate()
        policy=sign_policy(ir,policy_key,key_id="policy",service="example",
            environment="test",sequence=1,issued_at=START,expires_at=END)
        signed_witnesses=sign_attestation(
            witnesses,observations,evidence_key,key_id="attestor",
            policy_signature=policy["signature"],service="example",
            environment="test",nonce="witness-1",issued_at=START,expires_at=END)
        signed_roots=sign_attestation(
            [],{"custody_roots":custody_manifest},custodian_key,key_id="custodian",
            policy_signature=policy["signature"],service="example",
            environment="test",nonce="custody-1",issued_at=START,expires_at=END)
        with tempfile.TemporaryDirectory() as tmp:
            nonces=SQLiteNonceStore(Path(tmp)/"nonce.db")
            answer=attach_signed_governance(
                structural,reviewed_ir=ir,ir_binding=bound,
                evidence_pack=pack,witness_mapping=map_,
                signed_policy=policy,signed_observations=signed_witnesses,
                signed_custody=signed_roots,
                policy_keys={"policy":policy_key.public_key()},
                attestor_keys={"attestor":evidence_key.public_key()},
                custodian_keys={"custodian":custodian_key.public_key()},
                service="example",environment="test",minimum_sequence=1,
                nonce_accepted=nonces,witnesses=witnesses,
                observations=observations,source_bytes=blobs,as_of=NOW)
        self.assertEqual(answer["verdict"],"INCONCLUSIVE")
        self.assertFalse(answer["can_generate"])
        self.assertEqual(answer["custody"]["source_custody"]["verified_root_bytes"],5)
        self.assertEqual(answer["qualityrag_admission"],"INCONCLUSIVE")


if __name__=="__main__":
    unittest.main()
