import unittest
from pathlib import Path

from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import CsvOrderEventProvider


class DetectionPipelineTest(unittest.TestCase):
    def test_pipeline_ranks_suspicious_cancelled_orders_first(self):
        provider = CsvOrderEventProvider(Path("data/sample_order_events.csv"))
        results = DetectionPipeline(provider).run()

        self.assertTrue(results)
        self.assertGreater(results[0].risk_score, 0.8)
        self.assertIn("cancelled_near_touch", results[0].reasons)
        self.assertTrue(results[0].features.cancelled)

    def test_pipeline_keeps_filled_orders_lower_risk(self):
        provider = CsvOrderEventProvider(Path("data/sample_order_events.csv"))
        results = DetectionPipeline(provider).run()
        by_order_id = {result.order_id: result for result in results}

        self.assertLess(by_order_id["p-1004"].risk_score, by_order_id["p-1003"].risk_score)
        self.assertFalse(by_order_id["pm-2002"].features.cancelled)


if __name__ == "__main__":
    unittest.main()
