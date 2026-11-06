import unittest
from examples.protection_comparison import run_fixture


class ProtectionComparisonTests(unittest.TestCase):
    def test_fixture_is_transparent_about_limits(self):
        result = run_fixture()
        self.assertIn("synthetic", result["scope"])
        self.assertTrue(result["purpose_scoped"]["can_answer_payment_deadline"])
        self.assertTrue(result["purpose_scoped"]["can_answer_expiry_valid"])
        self.assertNotIn("payment_ref", result["purpose_scoped"]["exposed_fields"])
        self.assertNotIn("last_four", result["purpose_scoped"]["exposed_fields"])
        self.assertGreater(
            result["tokenization_plus_attributes"]["exposed_field_count"],
            result["purpose_scoped"]["exposed_field_count"])


if __name__ == "__main__":
    unittest.main()
