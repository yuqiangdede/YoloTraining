import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Asset, DatasetVersion, ModelArtifact


class TrainingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root, start_worker=False)
        self.client = TestClient(self.app)
        snapshot = self.root / "data" / "datasets" / "dataset-1"
        snapshot.mkdir(parents=True)
        (snapshot / "data.yaml").write_text("names: {0: car}\n", encoding="utf-8")
        model = self.root / "models" / "pretrained" / "yolo26n.pt"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"test model")
        with self.app.state.database.session() as session:
            session.add(DatasetVersion(
                id="dataset-1", name="roads", task="detect",
                snapshot_path="data/datasets/dataset-1", content_hash="a" * 64,
                manifest_json=json.dumps({"task": "detect"}), asset_count=1,
            ))
            session.commit()

    def tearDown(self) -> None:
        self.client.close()
        self.app.state.database.engine.dispose()
        self.temp.cleanup()

    def test_create_cancel_and_resume_training_job(self) -> None:
        created = self.client.post("/api/v1/training-jobs", json={
            "name": "roads-nano",
            "datasetVersionId": "dataset-1",
            "task": "detect",
            "modelPath": "models/pretrained/yolo26n.pt",
            "epochs": 2,
            "imgsz": 640,
            "batch": 2,
        })
        self.assertEqual(created.status_code, 201)
        job_id = created.json()["id"]
        self.assertEqual(created.json()["status"], "QUEUED")
        cancelled = self.client.post(f"/api/v1/training-jobs/{job_id}/cancel")
        self.assertEqual(cancelled.json()["status"], "CANCELLED")

    def test_rejects_task_mismatch(self) -> None:
        response = self.client.post("/api/v1/training-jobs", json={
            "name": "bad",
            "datasetVersionId": "dataset-1",
            "task": "segment",
            "modelPath": "models/pretrained/yolo26n-seg.pt",
            "epochs": 2,
            "imgsz": 640,
            "batch": 2,
        })
        self.assertEqual(response.status_code, 422)

    def test_create_onnx_export_job_for_project_model(self) -> None:
        model = self.root / "models" / "trained" / "best.pt"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"trained model")
        with self.app.state.database.session() as session:
            session.add(ModelArtifact(
                id="artifact-1", training_job_id=str(uuid4()), task="detect", name="best.pt",
                path="models/trained/best.pt", kind="PT", sha256="b" * 64, metrics_json="{}",
            ))
            session.commit()
        response = self.client.post("/api/v1/models/artifact-1/exports", json={"format": "onnx", "imgsz": 640})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "QUEUED")
        download = self.client.get("/api/v1/models/artifact-1/download")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"trained model")

    def test_create_prelabel_job_without_overwriting_human_labels(self) -> None:
        with self.app.state.database.session() as session:
            session.add(Asset(
                id="asset-1", filename="one.jpg", storage_path="uploads/assets/one.jpg",
                sha256="c" * 64, mime_type="image/jpeg", width=32, height=32, size_bytes=4,
            ))
            session.commit()
        response = self.client.post("/api/v1/prelabel-jobs", json={
            "modelPath": "models/pretrained/yolo26n.pt",
            "task": "detect",
            "assetIds": ["asset-1"],
            "confidence": 0.25,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "QUEUED")


if __name__ == "__main__":
    unittest.main()
