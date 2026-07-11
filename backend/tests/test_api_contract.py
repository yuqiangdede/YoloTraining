import unittest

from app.schemas.training import TASK_MODEL_SUFFIX, TrainRequest


class TrainingContractTests(unittest.TestCase):
    def test_model_must_match_dataset_task(self) -> None:
        request = TrainRequest(
            name="road-detect",
            dataset_version_id="dataset-1",
            task="detect",
            model_path="models/pretrained/yolo26n.pt",
            epochs=10,
            imgsz=640,
            batch=8,
        )
        self.assertEqual(request.task, "detect")
        self.assertEqual(TASK_MODEL_SUFFIX[request.task], ".pt")

    def test_rejects_segment_model_for_detection(self) -> None:
        with self.assertRaises(ValueError):
            TrainRequest(
                name="bad-run",
                dataset_version_id="dataset-1",
                task="detect",
                model_path="models/pretrained/yolo26n-seg.pt",
                epochs=10,
                imgsz=640,
                batch=8,
            )


if __name__ == "__main__":
    unittest.main()
