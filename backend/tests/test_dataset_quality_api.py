import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app


def image_bytes(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, format="PNG")
    return buffer.getvalue()


class DatasetQualityApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp.name), start_worker=False))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def create_dataset(self) -> dict:
        return self.client.post("/api/v1/datasets", json={"name": "quality", "task": "detect", "categories": [{"name": "car"}]}).json()["data"]

    def annotate(self, dataset_id: str, asset: dict, status: str = "COMPLETED") -> None:
        response = self.client.put(f"/api/v1/datasets/{dataset_id}/assets/{asset['id']}/annotation", json={
            "assetId": asset["id"], "task": "detect", "imageWidth": asset["width"], "imageHeight": asset["height"],
            "status": status, "shapes": [{"id": "shape-1", "labelId": self.category_id, "kind": "rectangle", "points": [[0.1, 0.1], [0.8, 0.8]]}],
        })
        self.assertEqual(response.status_code, 200)

    def test_completed_annotations_can_freeze_and_hash_is_idempotent(self) -> None:
        dataset = self.create_dataset()
        self.category_id = dataset["categories"][0]["id"]
        assets = []
        for name, color in [("one.png", "#111111"), ("two.png", "#222222")]:
            assets.append(self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={"files": (name, image_bytes(color), "image/png")}).json()["data"][0])
        for asset in assets:
            self.annotate(dataset["id"], asset)
        quality = self.client.get(f"/api/v1/datasets/{dataset['id']}/quality").json()["data"]
        self.assertEqual(quality["status"], "PASS")
        first = self.client.post(f"/api/v1/datasets/{dataset['id']}/versions", json={"name": "v1", "trainRatio": 0.5, "valRatio": 0.5, "testRatio": 0, "seed": 7})
        self.assertEqual(first.status_code, 201)
        second = self.client.post(f"/api/v1/datasets/{dataset['id']}/versions", json={"name": "v1-again", "trainRatio": 0.5, "valRatio": 0.5, "testRatio": 0, "seed": 7})
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["contentHash"], second.json()["contentHash"])

    def test_missing_annotation_blocks_quality_and_version(self) -> None:
        dataset = self.create_dataset()
        for name, color in [("one.png", "#111111"), ("two.png", "#222222")]:
            self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={"files": (name, image_bytes(color), "image/png")})
        quality = self.client.get(f"/api/v1/datasets/{dataset['id']}/quality").json()["data"]
        self.assertEqual(quality["status"], "BLOCKED")
        version = self.client.post(f"/api/v1/datasets/{dataset['id']}/versions", json={"name": "blocked", "trainRatio": 0.5, "valRatio": 0.5, "testRatio": 0})
        self.assertEqual(version.status_code, 422)

    def test_dataset_export_creates_downloadable_archive(self) -> None:
        dataset = self.create_dataset()
        self.category_id = dataset["categories"][0]["id"]
        assets = [self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={"files": (name, image_bytes(color), "image/png")}).json()["data"][0] for name, color in [("one.png", "#111111"), ("two.png", "#222222")]]
        for asset in assets:
            self.annotate(dataset["id"], asset)
        version = self.client.post(f"/api/v1/datasets/{dataset['id']}/versions", json={"name": "v1", "trainRatio": 0.5, "valRatio": 0.5, "testRatio": 0}).json()
        export = self.client.post(f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/exports", json={"format": "platform_json"})
        self.assertEqual(export.status_code, 201)
        self.assertEqual(export.json()["status"], "SUCCEEDED")
        downloaded = self.client.get(f"/api/v1/datasets/{dataset['id']}/exports/{export.json()['id']}/download")
        self.assertEqual(downloaded.status_code, 200)
        self.assertGreater(len(downloaded.content), 20)


if __name__ == "__main__":
    unittest.main()
