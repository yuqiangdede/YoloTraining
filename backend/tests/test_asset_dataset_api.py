import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.services.dataset_builder import _split_assets


def image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), "#d97706").save(buffer, format="PNG")
    return buffer.getvalue()


class AssetDatasetApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.client = TestClient(create_app(self.root))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def test_upload_deduplicates_by_content_hash(self) -> None:
        first = self.client.post(
            "/api/v1/assets",
            files={"files": ("sample.png", image_bytes(), "image/png")},
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            "/api/v1/assets",
            files={"files": ("copy.png", image_bytes(), "image/png")},
        )
        self.assertEqual(second.status_code, 409)
        listing = self.client.get("/api/v1/assets?page=1&pageSize=20")
        self.assertEqual(listing.json()["pagination"]["totalItems"], 1)

    def test_annotation_then_immutable_dataset_snapshot(self) -> None:
        upload = self.client.post(
            "/api/v1/assets",
            files={"files": ("sample.png", image_bytes(), "image/png")},
        ).json()
        asset_id = upload["data"][0]["id"]
        annotation = {
            "assetId": asset_id,
            "task": "detect",
            "imageWidth": 64,
            "imageHeight": 48,
            "status": "REVIEWED",
            "shapes": [{
                "id": "shape-1",
                "labelId": "car",
                "kind": "rectangle",
                "points": [[0.1, 0.1], [0.8, 0.8]],
            }],
        }
        saved = self.client.put(f"/api/v1/assets/{asset_id}/annotation", json=annotation)
        self.assertEqual(saved.status_code, 200)
        snapshot = self.client.post("/api/v1/datasets", json={
            "name": "roads-v1",
            "task": "detect",
            "assetIds": [asset_id],
            "classes": [{"id": "car", "name": "车辆"}],
            "trainRatio": 0.8,
            "valRatio": 0.2,
            "testRatio": 0.0,
            "seed": 7,
        })
        self.assertEqual(snapshot.status_code, 201)
        body = snapshot.json()
        self.assertTrue(body["contentHash"])
        snapshot_dir = self.root / body["snapshotPath"]
        self.assertTrue((snapshot_dir / "data.yaml").exists())
        self.assertTrue((snapshot_dir / "labels" / "train" / "sample.txt").exists())

    def test_unannotated_asset_returns_empty_document_without_404(self) -> None:
        upload = self.client.post(
            "/api/v1/assets",
            files={"files": ("sample.png", image_bytes(), "image/png")},
        ).json()
        asset_id = upload["data"][0]["id"]
        response = self.client.get(f"/api/v1/assets/{asset_id}/annotation")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["data"])

    def test_two_assets_keep_a_validation_sample_when_validation_is_enabled(self) -> None:
        assets = [SimpleNamespace(sha256="a"), SimpleNamespace(sha256="b")]
        splits = _split_assets(assets, train_ratio=0.8, val_ratio=0.2, test_ratio=0.0, seed=7)
        self.assertEqual(len(splits["train"]), 1)
        self.assertEqual(len(splits["val"]), 1)


if __name__ == "__main__":
    unittest.main()
