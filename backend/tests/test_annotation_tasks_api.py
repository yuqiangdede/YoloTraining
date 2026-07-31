import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app


def image_bytes(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (24, 18), color).save(buffer, format="PNG")
    return buffer.getvalue()


class AnnotationTasksApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp.name), start_worker=False))
        self.dataset = self.client.post("/api/v1/datasets", json={
            "name": "tasks", "task": "detect", "categories": [{"name": "car"}],
        }).json()["data"]
        upload = self.client.post(f"/api/v1/datasets/{self.dataset['id']}/assets", files=[
            ("files", ("a.png", image_bytes("red"), "image/png")),
            ("files", ("b.png", image_bytes("blue"), "image/png")),
        ])
        self.assets = upload.json()["data"]

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def test_assigns_all_assets_and_tracks_completion_without_review(self) -> None:
        created = self.client.post(f"/api/v1/datasets/{self.dataset['id']}/annotation-tasks", json={
            "name": "第一批", "assignee": "张三",
        })
        self.assertEqual(created.status_code, 201)
        task = created.json()["data"]
        self.assertEqual((task["assetCount"], task["completedCount"], task["status"]), (2, 0, "NEW"))
        category_id = self.dataset["categories"][0]["id"]
        asset = self.assets[0]
        self.client.put(f"/api/v1/datasets/{self.dataset['id']}/assets/{asset['id']}/annotation", json={
            "assetId": asset["id"], "task": "detect", "imageWidth": 24, "imageHeight": 18,
            "status": "COMPLETED", "shapes": [{"id": "box", "labelId": category_id, "kind": "rectangle", "points": [[0.1, 0.1], [0.5, 0.5]]}],
        })
        reread = self.client.get(f"/api/v1/datasets/{self.dataset['id']}/annotation-tasks").json()["data"][0]
        self.assertEqual((reread["completedCount"], reread["progress"], reread["status"]), (1, 50, "IN_PROGRESS"))

    def test_rejects_assets_from_another_dataset(self) -> None:
        other = self.client.post("/api/v1/datasets", json={
            "name": "other", "task": "detect", "categories": [{"name": "car"}],
        }).json()["data"]
        response = self.client.post(f"/api/v1/datasets/{other['id']}/annotation-tasks", json={
            "name": "错误批次", "assetIds": [self.assets[0]["id"]],
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "INVALID_TASK_ASSETS")


if __name__ == "__main__":
    unittest.main()
