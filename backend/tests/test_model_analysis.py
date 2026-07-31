import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.model_analysis import box_iou, evaluate_sample


class ModelAnalysisTests(unittest.TestCase):
    def test_matches_by_class_and_iou(self) -> None:
        truth = [{"label": "car", "box": [0.1, 0.1, 0.5, 0.5]}, {"label": "person", "box": [0.6, 0.1, 0.9, 0.8]}]
        predictions = [{"label": "car", "box": [0.1, 0.1, 0.5, 0.5]}, {"label": "dog", "box": [0.6, 0.1, 0.9, 0.8]}]
        result = evaluate_sample(truth, predictions, 0.5)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 1, 1))
        self.assertEqual(box_iou(truth[0]["box"], predictions[0]["box"]), 1)

    def test_creates_a_queued_analysis_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "models" / "pretrained" / "yolo26n.pt"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"model")
            client = TestClient(create_app(root, start_worker=False))
            dataset = client.post("/api/v1/datasets", json={
                "name": "analysis", "task": "detect", "categories": [{"name": "car"}],
            }).json()["data"]
            response = client.post(f"/api/v1/datasets/{dataset['id']}/analysis-jobs", json={
                "modelId": "pretrained:yolo26n.pt", "confidence": 0.3, "iouThreshold": 0.5,
            })
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["data"]["status"], "QUEUED")
            self.assertEqual(len(client.get(f"/api/v1/datasets/{dataset['id']}/analysis-jobs").json()["data"]), 1)
            client.close()
            client.app.state.database.engine.dispose()


if __name__ == "__main__":
    unittest.main()
