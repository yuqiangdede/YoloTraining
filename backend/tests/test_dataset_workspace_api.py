import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app


def image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "#2563eb").save(buffer, format="PNG")
    return buffer.getvalue()


class DatasetWorkspaceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp.name), start_worker=False))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def test_create_workspace_then_imports_assets_into_it(self) -> None:
        created = self.client.post("/api/v1/datasets", json={
            "name": "roads", "task": "detect", "categories": [{"name": "car"}],
        })
        self.assertEqual(created.status_code, 201)
        dataset = created.json()["data"]
        self.assertEqual(dataset["assetCount"], 0)
        self.assertEqual(dataset["categories"][0]["name"], "car")

        upload = self.client.post(
            f"/api/v1/datasets/{dataset['id']}/assets",
            files={"files": ("road.png", image_bytes(), "image/png")},
        )
        self.assertEqual(upload.status_code, 201)
        listed = self.client.get(f"/api/v1/datasets/{dataset['id']}/assets")
        self.assertEqual([item["filename"] for item in listed.json()["data"]], ["road.png"])

    def test_workspace_with_a_training_job_cannot_be_deleted(self) -> None:
        dataset = self.client.post("/api/v1/datasets", json={
            "name": "protected", "task": "detect", "categories": [{"name": "car"}],
        }).json()["data"]
        database = self.client.app.state.database
        from app.models import DatasetVersion, TrainingJob
        with database.session() as session:
            session.add(DatasetVersion(id="version-1", dataset_id=dataset["id"], name="v1", task="detect", snapshot_path="data/datasets/version-1", content_hash="a" * 64, manifest_json="{}", asset_count=0))
            session.add(TrainingJob(id="job-1", name="train", dataset_version_id="version-1", task="detect", model_path="models/pretrained/yolo26n.pt", run_path="runs/job-1", status="SUCCEEDED", params_json="{}"))
            session.commit()
        deleted = self.client.delete(f"/api/v1/datasets/{dataset['id']}")
        self.assertEqual(deleted.status_code, 409)
        self.assertEqual(deleted.json()["error"]["code"], "DATASET_IN_USE")

    def test_dataset_settings_are_persisted(self) -> None:
        dataset = self.client.post("/api/v1/datasets", json={"name": "settings", "task": "detect", "categories": [{"name": "car"}]}).json()["data"]
        response = self.client.patch(f"/api/v1/datasets/{dataset['id']}", json={
            "name": dataset["name"], "prelabelModelPath": "models/pretrained/yolo26n.pt",
            "prelabelMode": "yolo", "prelabelConfidence": 0.4,
        })
        self.assertEqual(response.status_code, 200)
        reread = self.client.get(f"/api/v1/datasets/{dataset['id']}").json()["data"]
        self.assertEqual(reread["prelabelModelPath"], "models/pretrained/yolo26n.pt")
        self.assertEqual(reread["prelabelConfidence"], 0.4)

    def test_dataset_prelabel_queues_all_active_assets(self) -> None:
        dataset = self.client.post("/api/v1/datasets", json={"name": "prelabel", "task": "detect", "categories": [{"name": "car"}]}).json()["data"]
        model = self.temp.name and Path(self.temp.name) / "models" / "pretrained" / "detector.pt"
        model.parent.mkdir(parents=True, exist_ok=True); model.write_bytes(b"model")
        from PIL import Image
        import io
        def image(color: str) -> bytes:
            output = io.BytesIO(); Image.new("RGB", (8, 8), color).save(output, format="PNG"); return output.getvalue()
        first = self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={'files': ('one.png', image('#111'), 'image/png')}).json()['data'][0]
        second = self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={'files': ('two.png', image('#222'), 'image/png')}).json()['data'][0]
        self.client.delete(f"/api/v1/datasets/{dataset['id']}/assets/{second['id']}")
        queued = self.client.post(f"/api/v1/prelabel-jobs/datasets/{dataset['id']}", json={"modelPath": "models/pretrained/detector.pt"})
        self.assertEqual(queued.status_code, 201)
        self.assertEqual(queued.json()["datasetId"], dataset["id"])
        self.assertEqual(queued.json()["params"]["assetIds"], [first["id"]])

    def test_dataset_prelabel_defaults_to_n_model_and_replaces_legacy_size(self) -> None:
        dataset = self.client.post("/api/v1/datasets", json={
            "name": "legacy-prelabel", "task": "detect", "categories": [{"name": "car"}],
        }).json()["data"]
        model_dir = Path(self.temp.name) / "models" / "pretrained"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "yolo26n.pt").write_bytes(b"nano")
        (model_dir / "yolo26m.pt").write_bytes(b"medium")
        self.client.patch(f"/api/v1/datasets/{dataset['id']}", json={
            "name": dataset["name"], "prelabelModelPath": "models/pretrained/yolo26m.pt",
        })
        self.client.post(
            f"/api/v1/datasets/{dataset['id']}/assets",
            files={"files": ("road.png", image_bytes(), "image/png")},
        )

        queued = self.client.post(f"/api/v1/prelabel-jobs/datasets/{dataset['id']}", json={})

        self.assertEqual(queued.status_code, 201)
        self.assertEqual(queued.json()["modelPath"], "models/pretrained/yolo26n.pt")
        reread = self.client.get(f"/api/v1/datasets/{dataset['id']}").json()["data"]
        self.assertEqual(reread["prelabelModelPath"], "models/pretrained/yolo26n.pt")

    def test_segment_dataset_prelabel_defaults_to_n_segment_model(self) -> None:
        dataset = self.client.post("/api/v1/datasets", json={
            "name": "segment-prelabel", "task": "segment", "categories": [{"name": "road"}],
        }).json()["data"]
        model_dir = Path(self.temp.name) / "models" / "pretrained"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "yolo26n-seg.pt").write_bytes(b"nano-segment")
        self.client.post(
            f"/api/v1/datasets/{dataset['id']}/assets",
            files={"files": ("road.png", image_bytes(), "image/png")},
        )

        queued = self.client.post(f"/api/v1/prelabel-jobs/datasets/{dataset['id']}", json={})

        self.assertEqual(queued.status_code, 201)
        self.assertEqual(queued.json()["modelPath"], "models/pretrained/yolo26n-seg.pt")

    def test_detection_dataset_accepts_sam_and_keeps_detection_task(self) -> None:
        dataset = self.client.post("/api/v1/datasets", json={"name": "sam-detect", "task": "detect", "categories": [{"name": "car"}]}).json()["data"]
        model_dir = Path(self.temp.name) / "models" / "pretrained"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "sam3.pt").write_bytes(b"sam")
        image = self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={"files": ("one.png", image_bytes(), "image/png")}).json()["data"][0]
        queued = self.client.post(f"/api/v1/prelabel-jobs/datasets/{dataset['id']}", json={"mode": "sam", "confidence": 0.3})
        self.assertEqual(queued.status_code, 201)
        self.assertEqual(queued.json()["task"], "detect")
        self.assertEqual(queued.json()["params"]["assetIds"], [image["id"]])


if __name__ == "__main__":
    unittest.main()
