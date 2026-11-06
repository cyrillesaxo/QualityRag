import unittest

from qualityrag.protection import ProtectionDenied
from qualityrag.protected_metadata import ProtectedPayment, SyntheticMetadataProvider


class ProtectedMetadataTests(unittest.TestCase):
    def setUp(self):
        self.payment = ProtectedPayment(
            "ref_example_payment_00001", "tenant-a", "visa", "4242", True)
        self.provider = SyntheticMetadataProvider([self.payment])

    def test_only_safe_attributes(self):
        p = self.provider.get_protected_payment(
            tenant="tenant-a", reference="ref_example_payment_00001")
        self.assertEqual(set(p.attributes()), {
            "payment_ref", "card_brand", "last_four", "expiry_valid"})
        self.assertFalse(any("pan" in k or "secret" in k for k in p.attributes()))

    def test_tenant_separation(self):
        with self.assertRaisesRegex(ProtectionDenied, "NOT_FOUND"):
            self.provider.get_protected_payment(
                tenant="tenant-b", reference=self.payment.reference)

    def test_no_plaintext_reveal_api(self):
        self.assertFalse(hasattr(self.provider, "detokenize"))
        self.assertFalse(hasattr(self.provider, "decrypt"))
        self.assertFalse(hasattr(self.provider, "reveal"))

    def test_duplicate_reference_denied(self):
        with self.assertRaisesRegex(ProtectionDenied, "DUPLICATE_REFERENCE"):
            SyntheticMetadataProvider([self.payment, self.payment])

    def test_full_pan_not_accepted_as_reference(self):
        with self.assertRaisesRegex(ProtectionDenied, "INVALID_PROTECTED_PAYMENT"):
            ProtectedPayment("4111111111111111", "tenant-a", "visa", "1111", True)

    def test_bad_last_four_and_boolean_type_denied(self):
        with self.assertRaises(ProtectionDenied):
            ProtectedPayment("ref_example_payment_00001", "tenant-a", "visa", "12345", True)
        with self.assertRaises(ProtectionDenied):
            ProtectedPayment("ref_example_payment_00001", "tenant-a", "visa", "4242", "true")


if __name__ == "__main__":
    unittest.main()
