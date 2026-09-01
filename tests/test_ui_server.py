import unittest

from spoof_liquidity_detector.ui_server import sample_account_profiles


class UiServerTest(unittest.TestCase):
    def test_loads_sample_account_profiles_for_dashboard(self):
        rows = sample_account_profiles(top=3)

        self.assertEqual(len(rows), 3)
        self.assertIn("maker", rows[0])
        self.assertIn("account_risk_score", rows[0])
        self.assertIn("far_order_ratio", rows[0])
        self.assertIsInstance(rows[0]["reasons"], list)


if __name__ == "__main__":
    unittest.main()
