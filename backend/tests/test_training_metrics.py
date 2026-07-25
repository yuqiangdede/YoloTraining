import unittest

from app.services.training_metrics import summarize_results


class TrainingMetricsTests(unittest.TestCase):
    def test_detection_prefers_box_map_and_tracks_best_epoch(self) -> None:
        result = summarize_results([
            {"epoch": "1", "metrics/mAP50(B)": "0.40", "metrics/mAP50-95(B)": "0.20", "metrics/precision(B)": "0.5", "val/box_loss": "1.2"},
            {"epoch": "2", "metrics/mAP50(B)": "0.60", "metrics/mAP50-95(B)": "0.35", "metrics/precision(B)": "0.7", "val/box_loss": "0.8"},
            {"epoch": "3", "metrics/mAP50(B)": "0.58", "metrics/mAP50-95(B)": "0.30", "metrics/precision(B)": "0.68", "val/box_loss": "0.9"},
        ], "detect")

        self.assertEqual(result["state"], "SUFFICIENT")
        self.assertEqual(result["primaryMetric"], "metrics/mAP50-95(B)")
        self.assertEqual(result["bestEpoch"], 2)
        self.assertEqual(result["bestValue"], 0.35)
        self.assertEqual(result["finalValue"], 0.30)
        self.assertEqual(result["validationMetrics"]["metrics/precision(B)"], 0.68)

    def test_segmentation_prefers_mask_metrics(self) -> None:
        result = summarize_results([
            {"epoch": "1", "metrics/mAP50(B)": "0.70", "metrics/mAP50-95(B)": "0.40", "metrics/mAP50(M)": "0.62", "metrics/mAP50-95(M)": "0.31"},
        ], "segment")

        self.assertEqual(result["primaryMetric"], "metrics/mAP50-95(M)")
        self.assertEqual(result["bestValue"], 0.31)

    def test_missing_or_non_numeric_results_are_incomplete(self) -> None:
        self.assertEqual(summarize_results([], "detect")["state"], "INCOMPLETE")
        result = summarize_results([{"epoch": "1", "metrics/mAP50-95(B)": "nan"}], "detect")
        self.assertEqual(result["state"], "INCOMPLETE")
        self.assertIn("PRIMARY_VALIDATION_METRIC_INVALID", result["notes"])

    def test_incomplete_training_is_not_ready(self) -> None:
        result = summarize_results([], "detect", completed=False)
        self.assertEqual(result["state"], "NOT_READY")


if __name__ == "__main__":
    unittest.main()
