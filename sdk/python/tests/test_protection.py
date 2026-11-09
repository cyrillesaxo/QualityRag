import unittest

from qualityrag.protection import Principal, ProtectionDenied, protect, authorize_release, SCHEMA


class PurposeProtectionTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal("analyst-a", "tenant-a", frozenset({"contract_review"}))
        self.record = {"payment_ref": "ref_abcdef123456", "last_four": "4242",
                       "payment_terms": "Payment due in 30 days"}
        self.contract = {
            "schema": SCHEMA, "tenant": "tenant-a", "authenticated": True,
            "fields": {
                "payment_ref": {"classification": "pci", "mode": "reference",
                    "grants": [{"purpose": "contract_review", "destination": "llm",
                                "operation": "read"}]},
                "last_four": {"classification": "pci", "mode": "derived",
                    "grants": [{"purpose": "contract_review", "destination": "llm",
                                "operation": "read"}]},
                "payment_terms": {"classification": "public", "mode": "plain",
                    "grants": [{"purpose": "contract_review", "destination": "llm",
                                "operation": "read"}]},
            }
        }

    def test_approved_minimum_view(self):
        out = protect(self.record, self.contract, self.principal,
                      purpose="contract_review", destination="llm")
        self.assertEqual(out["view"], self.record)
        self.assertEqual(authorize_release(out, self.principal, destination="llm",
                                           purpose="contract_review")["decision"],
                         "ALLOW_REFERENCE_ONLY")

    def test_reject_raw_pan_even_when_declared_reference(self):
        self.record["payment_ref"] = "4111111111111111"
        with self.assertRaises(ProtectionDenied):
            self.run_protect()

    def test_reject_unknown_field(self):
        self.record["unknown"] = "123"
        with self.assertRaisesRegex(ProtectionDenied, "UNCLASSIFIED_FIELD"):
            self.run_protect()

    def test_reject_missing_authentication(self):
        self.contract["authenticated"] = False
        with self.assertRaisesRegex(ProtectionDenied, "UNVERIFIED_CONTRACT"):
            self.run_protect()

    def test_reject_cross_tenant(self):
        other = Principal("analyst-b", "tenant-b", frozenset({"contract_review"}))
        with self.assertRaises(ProtectionDenied):
            protect(self.record, self.contract, other,
                    purpose="contract_review", destination="llm")

    def test_deny_unauthorized_destination(self):
        self.assertEqual(self.run_protect(destination="attacker")["view"], {})

    def test_reject_unapproved_purpose(self):
        with self.assertRaisesRegex(ProtectionDenied, "PURPOSE_NOT_GRANTED"):
            self.run_protect(purpose="export")

    def test_reject_plaintext_pci(self):
        self.contract["fields"]["payment_ref"]["mode"] = "plain"
        with self.assertRaisesRegex(ProtectionDenied, "SENSITIVE_PLAINTEXT_DENIED"):
            self.run_protect()

    def test_reject_wrong_derived_type(self):
        self.record["last_four"] = "12345"
        with self.assertRaisesRegex(ProtectionDenied, "INVALID_DERIVED_ATTRIBUTE"):
            self.run_protect()

    def test_release_denies_wrong_destination_or_operation(self):
        view = self.run_protect()
        with self.assertRaises(ProtectionDenied):
            authorize_release(view, self.principal, destination="other",
                              purpose="contract_review")
        with self.assertRaises(ProtectionDenied):
            authorize_release(view, self.principal, destination="llm",
                              purpose="contract_review", operation="detokenize")

    def run_protect(self, *, destination="llm", purpose="contract_review"):
        return protect(self.record, self.contract, self.principal,
                       purpose=purpose, destination=destination)


if __name__ == "__main__":
    unittest.main()
