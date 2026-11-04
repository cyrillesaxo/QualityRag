from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from tools.activation_runtime.preservation import make_contract,audit_output,observation
from tools.activation_runtime.interpreter import execute_plan,exhaustive_equivalence
from tools.activation_runtime.adapters import ingest
from test_runtime import policy


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.raw=b'{"actor":"supplier","recipient":"buyer","instruction":"must NOT disclose","amount":1,"unit":"mg"}'
        self.ir=policy()
        self.fields=["actor","recipient","instruction","amount","unit"]
        self.contract=make_contract(self.raw,task="contract",author="author",reviewer="reviewer",tenant="tenant",
            ir=self.ir,obligations=[{"field":f,"ir_node_id":"custody","mode":"EXACT","tolerance":None,"omission_permitted":False} for f in self.fields])

    def test_executable_dsl_and_role_inversion(self):
        result=execute_plan(self.raw,plan=[{"op":"PRESERVE","fields":self.fields},
            {"op":"TRANSITION","mapping":{f:str(i) for i,f in enumerate(self.fields)}},
            {"op":"ACTIVATE","runtime":"finite-json/v1"},{"op":"VERIFY"}],contract=self.contract,ir=self.ir)
        self.assertEqual(result["finite_constraint_result"],"SAT")
        bad={**result["output"],"actor":"buyer","recipient":"supplier"}
        self.assertEqual(audit_output(self.raw,bad,self.contract,current_ir=self.ir)["finite_constraint_result"],"UNSAT")
        with self.assertRaises(ValueError):
            execute_plan(self.raw,plan=[{"op":"EVAL","code":"arbitrary"}],contract=self.contract,ir=self.ir)

    def test_unknown_field_not_disposable_and_policy_invalidation(self):
        output={"actor":"supplier"}
        audit=audit_output(self.raw,output,self.contract,current_ir=self.ir)
        self.assertIn("unit",audit["residual_required"])
        changed={**self.ir,"ir_sha256":"0"*64}
        with self.assertRaises(ValueError):audit_output(self.raw,output,self.contract,current_ir=changed)

    def test_exact_unicode_character_and_byte_anchors(self):
        raw="é NOT".encode()
        obs=observation(raw,observation_id="negation",quote_start=2,quote_end=5,kind="EVENT",
            value="NOT",roles={"actor":"nurse"},polarity="NEGATIVE",quantity=None,unit=None,
            temporal_order=[],modality="PROHIBITED")
        self.assertEqual(obs["source"]["byte_start"],3)
        self.assertEqual(obs["source"]["quote"],"NOT")

    def test_exhaustive_counterexample_all_pairs(self):
        result=exhaustive_equivalence([["a","p","b"]],[["b","p","a"]],nodes=["a","b"],relations=["p"])
        self.assertEqual(result["checked_queries"],4)
        self.assertEqual(len(result["counterexamples"]),2)

    def test_pdf_and_text_adapters_repeated_headings(self):
        from reportlab.pdfgen import canvas
        data=BytesIO();pdf=canvas.Canvas(data)
        pdf.drawString(40,700,"Heading");pdf.showPage();pdf.drawString(40,700,"Heading");pdf.save()
        result=ingest(data.getvalue(),format="pdf")
        self.assertEqual([s["page"] for s in result["spans"]],[1,2])
        self.assertEqual(len(ingest(b"Heading\nHeading\n",format="text")["spans"]),2)
        with self.assertRaises(Exception):ingest(b"not a pdf",format="pdf")


class ExecutableFallbackTests(unittest.TestCase):
    setUp=PreservationTests.setUp
    def test_actual_failed_candidate_uses_checked_fallback_once(self):
        mapping={field:str(i) for i,field in enumerate(self.fields)}
        candidate={target:"corrupt" for target in mapping.values()}
        plan=[{"op":"TRANSITION","mapping":mapping},{"op":"ACTIVATE","runtime":"finite-json/v1","payload":candidate},
              {"op":"VERIFY"},{"op":"FALLBACK","baseline":"original-source"}]
        result=execute_plan(self.raw,plan=plan,contract=self.contract,ir=self.ir)
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["output"]["actor"],"supplier")
        self.assertEqual(result["checks"][0]["finite_constraint_result"],"UNSAT")
        without=execute_plan(self.raw,plan=plan[:-1],contract=self.contract,ir=self.ir)
        self.assertEqual(without["action"],"REFUSE")
        self.assertEqual(without["finite_constraint_result"],"UNSAT")


class SignedBindingTests(unittest.TestCase):
    setUp=PreservationTests.setUp
    def test_review_signature_binds_exact_source_policy_and_obligations(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from tools.activation_runtime.preservation import bind_reviewed_contract
        from tools.activation_runtime.authority import review_binding
        from tools.activation_runtime.common import fingerprint
        from signed_gate import SQLiteNonceStore
        reviewer=Ed25519PrivateKey.generate();author=Ed25519PrivateKey.generate()
        context={"source_sha256":self.contract["source_sha256"],"policy_ir_sha256":self.ir["ir_sha256"],
                 "policy_source_sha256":self.ir["source"]["sha256"],"contract_sha256":fingerprint(self.contract)}
        signed=review_binding(context,decision="APPROVE",reviewer="reviewer",author_key_id="author",key=reviewer,key_id="reviewer",
            issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce="contract-review")
        with tempfile.TemporaryDirectory() as root:
            nonce=SQLiteNonceStore(Path(root)/"nonce.sqlite")
            result=bind_reviewed_contract(self.raw,self.contract,self.ir,signed_review=signed,reviewer_keys={"reviewer":reviewer.public_key()},
                author_public_key=author.public_key(),as_of="2026-11-04T12:00:00Z",nonce_store=nonce)
            self.assertEqual(result["review"]["review"],"HOST_AUTHORIZED_APPROVAL")
            self.assertFalse(result["can_generate"])
