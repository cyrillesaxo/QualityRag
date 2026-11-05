"""Omission requires an independent one-time signature over this exact output."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.common import canonical
from tools.activation_runtime.preservation import make_contract,audit_output,omission_context,bind_reviewed_contract
from tools.activation_runtime.authority import review_binding
from signed_gate import SQLiteNonceStore
from test_runtime import policy


class OmissionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.ir=policy();self.values={"instruction":"must NOT disclose","amount":0.3,"uncertain":None,"unit":"mg"}
        self.raw=canonical(self.values);self.contract=self.contract_for(self.raw)
        self.output={key:value for key,value in self.values.items() if key!="amount"}
        self.author=Ed25519PrivateKey.generate();self.reviewer=Ed25519PrivateKey.generate()
        self.keys={"review-key":self.reviewer.public_key()};self.subjects={"review-key":"reviewer"}
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.nonces=SQLiteNonceStore(Path(self.temp.name)/"nonce.sqlite")

    def contract_for(self,raw,tolerance=0.1):
        import json
        return make_contract(raw,task="audit",author="author",reviewer="reviewer",tenant="tenant",ir=self.ir,
            obligations=[{"field":field,"ir_node_id":"custody","mode":"APPROXIMATE" if field=="amount" else ("UNKNOWN" if field=="uncertain" else "EXACT"),
                          "tolerance":tolerance if field=="amount" else None,"omission_permitted":field=="amount"} for field in json.loads(raw)])

    def signed(self,*,context=None,reviewer="reviewer",key=None,decision="APPROVE",nonce="omit-1"):
        return review_binding(omission_context(self.raw,self.output,self.contract,current_ir=self.ir) if context is None else context,
            decision=decision,reviewer=reviewer,author_key_id="author-key",key=self.reviewer if key is None else key,
            key_id="review-key",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce=nonce)

    def audit(self,*,signed=None,output=None,contract=None,**changes):
        args={"current_ir":self.ir,"signed_omission_review":signed,"reviewer_keys":self.keys,
              "reviewer_subjects":self.subjects,"author_public_key":self.author.public_key(),
              "as_of":"2026-11-04T12:00:00Z","nonce_store":self.nonces};args.update(changes)
        return audit_output(self.raw,self.output if output is None else output,self.contract if contract is None else contract,**args)

    def test_unsigned_omission_is_unsat_and_boolean_approval_refuses(self):
        row=self.audit();self.assertEqual(row["finite_constraint_result"],"UNSAT")
        self.assertIn("amount",row["residual_required"]);self.assertEqual(row["omitted"],[])
        for flag in (True,"reviewed",1,0,None):
            with self.assertRaises(PermissionError):self.audit(omission_reviewed=flag)

    def test_exact_output_review_authorizes_only_declared_omission_once(self):
        signed=self.signed();row=self.audit(signed=signed)
        self.assertEqual(row["finite_constraint_result"],"SAT")
        self.assertEqual([(o["field"],o["ir_node_id"]) for o in row["omitted"]],[("amount","custody")])
        omitted=row["omitted"][0]
        self.assertEqual(omitted["location"],next(o["anchor"] for o in self.contract["obligations"] if o["field"]=="amount"))
        self.assertEqual(omitted["refetch"],{"method":"REFETCH_FROM_CUSTODY","source_sha256":self.contract["source_sha256"]})
        self.assertEqual(row["omission_review"]["reviewer"],"reviewer")
        self.assertEqual(row["qualityrag_admission"],"INCONCLUSIVE");self.assertFalse(row["can_generate"])
        with self.assertRaises(PermissionError):self.audit(signed=signed)

    def test_review_output_hash_prevents_reuse_for_other_valid_approximation(self):
        # Include one approximate field and omit another, so both candidates are otherwise valid.
        self.values["optional"]=1;self.raw=canonical(self.values)
        rows=[{k:v for k,v in r.items() if k!="anchor"} for r in self.contract_for(self.raw)["obligations"]]
        next(row for row in rows if row["field"]=="optional").update(mode="APPROXIMATE",tolerance=0,omission_permitted=True)
        self.contract=make_contract(self.raw,task="audit",author="author",reviewer="reviewer",tenant="tenant",ir=self.ir,obligations=rows)
        self.output={k:v for k,v in self.values.items() if k!="optional"};signed=self.signed()
        with self.assertRaises(PermissionError):self.audit(signed=signed,output={**self.output,"amount":0.4})
        self.assertEqual(self.audit(signed=signed)["finite_constraint_result"],"SAT")

    def test_wrong_omission_set_refuses_without_consuming_review(self):
        signed=self.signed();changed={k:v for k,v in self.output.items() if k!="unit"}
        with self.assertRaises(ValueError):self.audit(signed=signed,output=changed)
        self.assertEqual(self.audit(signed=signed)["finite_constraint_result"],"SAT")

    def test_invalid_retained_value_or_invention_cannot_use_review(self):
        signed=self.signed()
        for changed in ({**self.output,"instruction":"may disclose"},{**self.output,"invented":"claim"}):
            with self.assertRaises(ValueError):self.audit(signed=signed,output=changed)
        self.assertEqual(self.audit(signed=signed)["finite_constraint_result"],"SAT")

    def test_host_subject_and_contract_reviewer_must_match_signer(self):
        signed=self.signed()
        for subjects in (None,{}, {"review-key":"other"}):
            with self.assertRaises(PermissionError):self.audit(signed=signed,reviewer_subjects=subjects)
        with self.assertRaises(PermissionError):self.audit(signed=self.signed(reviewer="other"))
        contract={**self.contract,"reviewer":"other"}
        context=omission_context(self.raw,self.output,contract,current_ir=self.ir)
        with self.assertRaises(PermissionError):self.audit(signed=self.signed(context=context),contract=contract)
        self.assertEqual(self.audit(signed=signed)["finite_constraint_result"],"SAT")

    def test_same_author_key_under_reviewer_alias_cannot_approve(self):
        with self.assertRaises(PermissionError):self.audit(signed=self.signed(key=self.author),reviewer_keys={"review-key":self.author.public_key()})
        self.assertEqual(self.audit(signed=self.signed())["finite_constraint_result"],"SAT")

    def test_expiry_revocation_rejection_and_wrong_purpose_preserve_nonce(self):
        signed=self.signed()
        for changes in ({"as_of":"2026-11-06T00:00:00Z"},{"reviewer_keys":{},"reviewer_subjects":{}}):
            with self.assertRaises(ValueError):self.audit(signed=signed,**changes)
        with self.assertRaises(PermissionError):self.audit(signed=self.signed(decision="REJECT"))
        context=omission_context(self.raw,self.output,self.contract,current_ir=self.ir);context["purpose"]="PRESERVATION_CONTRACT_REVIEW"
        with self.assertRaises(PermissionError):self.audit(signed=self.signed(context=context))
        self.assertEqual(self.audit(signed=signed)["finite_constraint_result"],"SAT")

    def test_contract_anchors_duplicates_and_defaults_are_reconstructed(self):
        mutations=[lambda d:d["obligations"][0]["anchor"].update(value_sha256="0"*64),
                   lambda d:d["obligations"].append(deepcopy(d["obligations"][0])),
                   lambda d:d.update(default_unspecified="DISCARD"),lambda d:d.update(version="2.0"),
                   lambda d:next(row for row in d["obligations"] if row["field"]=="instruction").update(omission_permitted=True)]
        for mutate in mutations:
            contract=deepcopy(self.contract);mutate(contract)
            with self.assertRaises(ValueError):self.audit(contract=contract)

    def test_ir_content_cannot_change_while_retaining_claimed_hash(self):
        ir=deepcopy(self.ir);ir["nodes"][0]["parameters"]["min_independent_sources"]=2
        with self.assertRaises(ValueError):self.audit(current_ir=ir)
        with self.assertRaises(ValueError):make_contract(self.raw,task="audit",author="author",reviewer="reviewer",tenant="tenant",ir=ir,obligations=[])

    def test_unknown_missing_fields_remain_unknown_and_require_residual(self):
        output={k:v for k,v in self.values.items() if k!="uncertain"}
        row=self.audit(output=output)
        self.assertIn("uncertain",row["unknown"]);self.assertIn("uncertain",row["residual_required"])
        self.assertEqual(row["finite_constraint_result"],"UNSAT")

    def test_decimal_tolerance_accepts_exact_boundary_and_refuses_just_outside(self):
        self.assertIn("amount",self.audit(output={**self.values,"amount":0.4})["approximated"])
        self.assertEqual(self.audit(output={**self.values,"amount":0.4000000000000001})["finite_constraint_result"],"UNSAT")
        self.assertEqual(self.audit(output={**self.values,"amount":True})["finite_constraint_result"],"UNSAT")

    def test_large_integer_tolerance_uses_exact_math_without_float_overflow(self):
        self.values["amount"]=10**400;self.raw=canonical(self.values);self.contract=self.contract_for(self.raw,tolerance=10**400)
        row=self.audit(output={**self.values,"amount":10**400+1})
        self.assertEqual(row["finite_constraint_result"],"SAT");self.assertIn("amount",row["approximated"])

    def test_nested_or_nonfinite_output_refuses_before_review_consumption(self):
        signed=self.signed()
        for output in ({**self.output,"unit":{}},{**self.output,"unit":float("nan")},{1:"bad"}):
            with self.assertRaises(ValueError):self.audit(signed=signed,output=output)
        self.assertEqual(self.audit(signed=signed)["finite_constraint_result"],"SAT")

    def test_unnecessary_omission_signature_refuses_and_empty_output_can_be_reviewed(self):
        with self.assertRaises(ValueError):self.audit(signed=self.signed(),output=self.values)
        raw=canonical({"amount":1});contract=self.contract_for(raw);context=omission_context(raw,{},contract,current_ir=self.ir)
        signed=self.signed(context=context)
        row=audit_output(raw,{},contract,current_ir=self.ir,signed_omission_review=signed,reviewer_keys=self.keys,
            reviewer_subjects=self.subjects,author_public_key=self.author.public_key(),as_of="2026-11-04T12:00:00Z",nonce_store=self.nonces)
        self.assertEqual(row["finite_constraint_result"],"SAT");self.assertFalse(row["can_generate"])

    def test_contract_review_does_not_authorize_omission(self):
        from tools.activation_runtime.common import fingerprint
        context={"purpose":"PRESERVATION_CONTRACT_REVIEW","source_sha256":self.contract["source_sha256"],
                 "policy_ir_sha256":self.ir["ir_sha256"],"policy_source_sha256":self.ir["source"]["sha256"],"contract_sha256":fingerprint(self.contract)}
        signed=self.signed(context=context)
        with self.assertRaises(PermissionError):self.audit(signed=signed)
        row=bind_reviewed_contract(self.raw,self.contract,self.ir,signed_review=signed,reviewer_keys=self.keys,
            reviewer_subjects=self.subjects,author_public_key=self.author.public_key(),as_of="2026-11-04T12:00:00Z",nonce_store=self.nonces)
        self.assertEqual(row["review"]["review"],"HOST_AUTHORIZED_APPROVAL")

    def test_missing_host_author_key_or_durable_nonce_store_refuses(self):
        signed=self.signed()
        for changes in ({"author_public_key":None},{"nonce_store":None}):
            with self.assertRaises(PermissionError):self.audit(signed=signed,**changes)
        self.assertEqual(self.audit(signed=signed)["finite_constraint_result"],"SAT")
