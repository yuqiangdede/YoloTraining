import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import Asset, Dataset, DatasetVersion, ExportJob, ModelArtifact, TrainingJob
from app.schemas.training import RFDETR_WEIGHTS


class TrainingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root, start_worker=False)
        self.client = TestClient(self.app)
        snapshot = self.root / "data" / "datasets" / "dataset-1"
        (snapshot / "images" / "train").mkdir(parents=True)
        (snapshot / "images" / "val").mkdir(parents=True)
        (snapshot / "images" / "train" / "one.png").write_bytes(b"image")
        (snapshot / "images" / "val" / "two.png").write_bytes(b"image")
        (snapshot / "data.yaml").write_text("names: {0: car}\n", encoding="utf-8")
        model = self.root / "models" / "pretrained" / "yolo26n.pt"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"test model")
        with self.app.state.database.session() as session:
            session.add(Dataset(id="workspace-1", name="roads-workspace", task="detect"))
            session.add(DatasetVersion(
                id="dataset-1", dataset_id="workspace-1", name="roads", task="detect",
                snapshot_path="data/datasets/dataset-1", content_hash="a" * 64,
                manifest_json=json.dumps({"task": "detect", "valRatio": 0.2}), asset_count=1,
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

    def test_accepts_albumentations_preset(self) -> None:
        created = self.client.post("/api/v1/training-jobs", json={
            "name": "roads-photometric",
            "datasetVersionId": "dataset-1",
            "task": "detect",
            "modelPath": "models/pretrained/yolo26n.pt",
            "augmentationPreset": "photometric",
        })
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["params"]["augmentationPreset"], "photometric")

    def test_rejects_unknown_albumentations_preset(self) -> None:
        response = self.client.post("/api/v1/training-jobs", json={
            "name": "roads-invalid-augmentation",
            "datasetVersionId": "dataset-1",
            "task": "detect",
            "modelPath": "models/pretrained/yolo26n.pt",
            "augmentationPreset": "spatial-magic",
        })
        self.assertEqual(response.status_code, 422)

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

    def test_returns_validation_details_for_invalid_advanced_parameter(self) -> None:
        response = self.client.post("/api/v1/training-jobs", json={
            "name": "bad-learning-rate",
            "datasetVersionId": "dataset-1",
            "task": "detect",
            "modelPath": "models/pretrained/yolo26n.pt",
            "lr0": 0,
        })

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(response.json()["error"]["details"][0]["loc"][-1], "lr0")

    def test_rejects_legacy_snapshot_without_validation_images(self) -> None:
        (self.root / "data" / "datasets" / "dataset-1" / "images" / "val" / "two.png").unlink()
        response = self.client.post("/api/v1/training-jobs", json={
            "name": "missing-validation",
            "datasetVersionId": "dataset-1",
            "task": "detect",
            "modelPath": "models/pretrained/yolo26n.pt",
            "epochs": 2,
            "imgsz": 640,
            "batch": 2,
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "INVALID_DATASET_SPLIT")

    def test_rfdetr_requires_local_weight_and_validation_and_reuses_queue(self) -> None:
        payload = {"engine": "rfdetr", "name": "roads-rfdetr", "datasetVersionId": "dataset-1",
                   "task": "detect", "modelPath": RFDETR_WEIGHTS}
        missing = self.client.post("/api/v1/training-jobs", json=payload)
        self.assertEqual(missing.json()["error"]["code"], "MODEL_NOT_FOUND")
        weight = self.root / RFDETR_WEIGHTS
        weight.parent.mkdir()
        weight.write_bytes(b"test model")
        with patch("app.api.training.find_spec", return_value=object()):
            response = self.client.post("/api/v1/training-jobs", json=payload)
        self.assertEqual(response.status_code, 201)
        job = response.json()
        self.assertEqual(job["engine"], "rfdetr")
        self.assertEqual(job["params"]["batch"], 2)
        self.assertNotIn("imgsz", job["params"])
        job_url = f"/api/v1/training-jobs/{job['id']}"
        self.assertEqual(self.client.post(job_url + "/pause").status_code, 422)
        self.assertEqual(self.client.post(job_url + "/resume").status_code, 422)
        self.assertEqual(self.client.post(job_url + "/cancel").json()["status"], "CANCELLED")
        (self.root / "data/datasets/dataset-1/images/val/two.png").unlink()
        missing = self.client.post("/api/v1/training-jobs", json=payload)
        self.assertEqual(missing.json()["error"]["code"], "INVALID_DATASET_SPLIT")

    def test_returns_job_error_and_log_content(self) -> None:
        from app.models import TrainingJob
        run_dir = self.root / "runs" / "failed-job"; run_dir.mkdir(parents=True)
        (run_dir / "train.log").write_text("first line\nvalidation images missing\n", encoding="utf-8")
        with self.app.state.database.session() as session:
            session.add(TrainingJob(id="failed-job", name="failed", dataset_version_id="dataset-1", task="detect", model_path="models/pretrained/yolo26n.pt", run_path="runs/failed-job", status="FAILED", params_json="{}", error_message="验证集没有图片"))
            session.commit()
        job = self.client.get("/api/v1/training-jobs/failed-job")
        self.assertEqual(job.json()["errorMessage"], "验证集没有图片")
        log = self.client.get("/api/v1/training-jobs/failed-job/log")
        self.assertEqual(log.status_code, 200)
        self.assertIn("validation images missing", log.json()["content"])

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

    def test_deletes_a_model_artifact_with_its_exports_but_keeps_training_job(self) -> None:
        from app.models import ExportJob, TrainingJob
        model = self.root / "models" / "trained" / "delete-me.pt"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"trained model")
        export_dir = self.root / "runs" / "exports" / "export-delete-me"
        export_dir.mkdir(parents=True)
        output = export_dir / "delete-me.onnx"
        output.write_bytes(b"onnx")
        with self.app.state.database.session() as session:
            session.add(TrainingJob(id="keep-job", name="keep", dataset_version_id="dataset-1", task="detect", model_path="models/pretrained/yolo26n.pt", run_path="runs/keep-job", status="SUCCEEDED", params_json="{}"))
            session.add(ModelArtifact(id="delete-me", training_job_id="keep-job", task="detect", name="delete-me.pt", path="models/trained/delete-me.pt", kind="PT", sha256="d" * 64, metrics_json="{}"))
            session.add(ExportJob(id="export-delete-me", artifact_id="delete-me", format="onnx", status="SUCCEEDED", params_json="{}", output_path="runs/exports/export-delete-me/delete-me.onnx"))
            session.commit()

        response = self.client.delete("/api/v1/models/delete-me")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(model.exists())
        self.assertFalse(export_dir.exists())
        self.assertEqual(self.client.get("/api/v1/training-jobs/keep-job").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/models").json()["data"], [])

    def test_collecting_pt_artifact_queues_onnx_export(self) -> None:
        from app.models import ExportJob, ModelArtifact, TrainingJob
        from app.services.training_worker import TrainingWorker

        run_dir = self.root / "runs" / "auto-export-job"
        run_dir.mkdir(parents=True)
        (run_dir / "best.pt").write_bytes(b"trained model")
        (run_dir / "results.csv").write_text(
            "epoch,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),val/box_loss\n"
            "1,0.6,0.5,0.7,0.4,1.0\n"
            "2,0.7,0.6,0.8,0.5,0.8\n",
            encoding="utf-8",
        )
        job = TrainingJob(
            id="auto-export-job", name="auto export", dataset_version_id="dataset-1", task="detect",
            model_path="models/pretrained/yolo26n.pt", run_path="runs/auto-export-job",
            status="SUCCEEDED", params_json="{}",
        )
        with self.app.state.database.session() as session:
            session.add(job)
            session.flush()
            TrainingWorker(self.root, self.app.state.database)._collect_artifacts(session, job, run_dir)
            session.commit()
            artifact = session.scalar(select(ModelArtifact).where(ModelArtifact.training_job_id == job.id))
            export = session.scalar(select(ExportJob).where(ExportJob.artifact_id == artifact.id))
            self.assertIsNotNone(export)
            self.assertEqual(export.status, "QUEUED")
            self.assertEqual(export.progress, 0)
            self.assertEqual(artifact.training_quality_json and json.loads(artifact.training_quality_json)["bestEpoch"], 2)
            self.assertEqual(json.loads(artifact.training_quality_json)["primaryMetric"], "metrics/mAP50-95(B)")

    def test_create_prelabel_job_without_overwriting_human_labels(self) -> None:
        with self.app.state.database.session() as session:
            session.add(Dataset(id="workspace-assets", name="assets-workspace", task="detect"))
            session.add(Asset(
                id="asset-1", dataset_id="workspace-assets", filename="one.jpg", storage_path="uploads/assets/one.jpg",
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

    def test_deletes_a_finished_training_job_with_its_artifacts_and_run_files(self) -> None:
        from app.models import ExportJob, TrainingJob
        run_dir = self.root / "runs" / "finished-job"
        run_dir.mkdir(parents=True)
        (run_dir / "best.pt").write_bytes(b"model")
        with self.app.state.database.session() as session:
            session.add(TrainingJob(id="finished-job", name="finished", dataset_version_id="dataset-1", task="detect", model_path="models/pretrained/yolo26n.pt", run_path="runs/finished-job", status="SUCCEEDED", params_json="{}"))
            session.add(ModelArtifact(id="artifact-finished", training_job_id="finished-job", task="detect", name="best.pt", path="runs/finished-job/best.pt", kind="PT", sha256="c" * 64, metrics_json="{}"))
            session.add(ExportJob(id="export-finished", artifact_id="artifact-finished", format="onnx", status="SUCCEEDED", params_json="{}", output_path="runs/exports/export-finished/best.onnx"))
            session.commit()

        response = self.client.delete("/api/v1/training-jobs/finished-job")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])
        self.assertFalse(run_dir.exists())
        self.assertEqual(self.client.get("/api/v1/training-jobs/finished-job").status_code, 404)

    def test_refuses_to_delete_a_running_training_job(self) -> None:
        from app.models import TrainingJob
        with self.app.state.database.session() as session:
            session.add(TrainingJob(id="running-job", name="running", dataset_version_id="dataset-1", task="detect", model_path="models/pretrained/yolo26n.pt", run_path="runs/running-job", status="RUNNING", params_json="{}"))
            session.commit()

        response = self.client.delete("/api/v1/training-jobs/running-job")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "JOB_RUNNING")

    def test_worker_selects_the_oldest_queued_work_across_training_and_exports(self) -> None:
        from app.models import ExportJob, TrainingJob
        from app.services.training_worker import TrainingWorker
        with self.app.state.database.session() as session:
            session.add(TrainingJob(id="new-training", name="new", dataset_version_id="dataset-1", task="detect", model_path="models/pretrained/yolo26n.pt", run_path="runs/new-training", status="QUEUED", params_json="{}"))
            session.flush()
            training = session.get(TrainingJob, "new-training")
            training.created_at = training.created_at + timedelta(minutes=1)
            session.add(ExportJob(id="old-export", artifact_id="missing", format="onnx", status="QUEUED", params_json="{}"))
            session.commit()
            kind, item = TrainingWorker(self.root, self.app.state.database)._next_queued(session)

        self.assertEqual(kind, "export")
        self.assertEqual(item.id, "old-export")

    def test_training_list_exposes_queue_position_and_worker_health(self) -> None:
        with self.app.state.database.session() as session:
            training = TrainingJob(
                id="visible-training", name="visible", dataset_version_id="dataset-1", task="detect",
                model_path="models/pretrained/yolo26n.pt", run_path="runs/visible-training",
                status="QUEUED", params_json="{}",
            )
            session.add(training)
            session.flush()
            training.created_at = training.created_at + timedelta(minutes=1)
            session.add(ExportJob(
                id="older-export", artifact_id="missing", format="onnx", status="QUEUED", params_json="{}",
            ))
            session.commit()

        response = self.client.get("/api/v1/training-jobs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        visible = next(item for item in payload["data"] if item["id"] == "visible-training")
        self.assertEqual(visible["queuePosition"], 2)
        self.assertEqual(visible["queueSize"], 2)
        self.assertIn("alive", payload["worker"])


if __name__ == "__main__":
    unittest.main()
