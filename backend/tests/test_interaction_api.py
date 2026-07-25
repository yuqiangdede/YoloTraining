import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.models import Annotation


def image_bytes(color: str = "#e36a22") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 16), color).save(output, format="PNG")
    return output.getvalue()


class InteractionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.client = TestClient(create_app(self.root, start_worker=False))
        self.dataset = self.client.post("/api/v1/datasets", json={
            "name": "interaction", "task": "detect", "categories": [{"name": "car"}],
        }).json()["data"]

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def upload(self, name: str, color: str) -> dict:
        return self.client.post(
            f"/api/v1/datasets/{self.dataset['id']}/assets",
            files={"files": (name, image_bytes(color), "image/png")},
        ).json()["data"][0]

    def test_annotation_counts_status_filter_and_restore(self) -> None:
        unlabeled = self.upload("unlabeled.png", "#111111")
        draft = self.upload("draft.png", "#222222")
        reviewed = self.upload("reviewed.png", "#333333")
        category_id = self.dataset["categories"][0]["id"]
        document = {
            "assetId": reviewed["id"], "task": "detect", "imageWidth": 24, "imageHeight": 16,
            "status": "REVIEWED", "shapes": [{"id": "shape", "labelId": category_id, "kind": "rectangle", "points": [[.1, .1], [.8, .8]]}],
        }
        self.client.put(f"/api/v1/datasets/{self.dataset['id']}/assets/{reviewed['id']}/annotation", json=document)
        document["assetId"] = draft["id"]
        document["status"] = "DRAFT"
        with self.client.app.state.database.session() as session:
            session.add(Annotation(id="draft-annotation", asset_id=draft["id"], task="detect", status="DRAFT", document_json=json.dumps(document)))
            session.commit()

        dataset = self.client.get(f"/api/v1/datasets/{self.dataset['id']}").json()["data"]
        self.assertEqual(dataset["annotationCounts"], {"unlabeled": 1, "draft": 1, "completed": 1, "reviewed": 0})
        filtered = self.client.get(
            f"/api/v1/datasets/{self.dataset['id']}/assets",
            params=[("annotationStatus", "UNLABELED"), ("annotationStatus", "DRAFT")],
        ).json()
        self.assertEqual({item["annotationStatus"] for item in filtered["data"]}, {"UNLABELED", "DRAFT"})
        self.assertEqual(filtered["pagination"]["totalItems"], 2)

        self.client.delete(f"/api/v1/datasets/{self.dataset['id']}/assets/{unlabeled['id']}")
        restored = self.client.patch(
            f"/api/v1/datasets/{self.dataset['id']}/assets/{unlabeled['id']}", json={"isDeleted": False},
        )
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(restored.json()["isDeleted"])

    def test_pretrained_metadata_rejections_and_prediction(self) -> None:
        model_dir = self.root / "models" / "pretrained"
        model_dir.mkdir(parents=True)
        (model_dir / "yolo26n.pt").write_bytes(b"model")
        (model_dir / "yolo26n-pose.pt").write_bytes(b"pose")
        (model_dir / "sam3.pt").write_bytes(b"sam")
        metadata = self.client.get("/api/v1/models").json()["pretrained"]
        by_id = {item["id"]: item for item in metadata}
        self.assertEqual(by_id["yolo26n.pt"]["task"], "detect")
        self.assertEqual(by_id["yolo26n-pose.pt"]["task"], "pose")
        self.assertTrue(by_id["yolo26n.pt"]["canTest"])
        self.assertFalse(by_id["sam3.pt"]["canTest"])

        self.assertEqual(self.client.post(
            "/api/v1/models/pretrained/unknown.pt/predict",
            files={"image": ("test.png", image_bytes(), "image/png")},
        ).status_code, 404)
        traversal = self.client.post(
            "/api/v1/models/pretrained/..%5Cyolo26n.pt/predict",
            files={"image": ("test.png", image_bytes(), "image/png")},
        )
        self.assertEqual(traversal.status_code, 404)
        self.assertEqual(traversal.json()["error"]["code"], "PRETRAINED_MODEL_NOT_FOUND")
        sam = self.client.post(
            "/api/v1/models/pretrained/sam3.pt/predict",
            files={"image": ("test.png", image_bytes(), "image/png")},
        )
        self.assertEqual(sam.status_code, 422)
        self.assertEqual(sam.json()["error"]["code"], "PRETRAINED_MODEL_NOT_TESTABLE")
        self.assertEqual(self.client.post(
            "/api/v1/models/pretrained/yolo26n.pt/predict", data={"confidence": "1.2"},
            files={"image": ("test.png", image_bytes(), "image/png")},
        ).json()["error"]["code"], "INVALID_CONFIDENCE")
        self.assertEqual(self.client.post(
            "/api/v1/models/pretrained/yolo26n.pt/predict",
            files={"image": ("test.txt", b"not-image", "text/plain")},
        ).json()["error"]["code"], "INVALID_IMAGE")

        fake_model = Mock()
        fake_model.predict.return_value = [object()]
        with patch("app.api.models._get_cached_model", return_value=fake_model), \
             patch("app.api.models._prediction_rows", return_value=[]), \
             patch("app.api.models._annotated_data_url", return_value="data:image/jpeg;base64,AA=="):
            success = self.client.post(
                "/api/v1/models/pretrained/yolo26n.pt/predict", data={"confidence": "0.4"},
                files={"image": ("test.png", image_bytes(), "image/png")},
            )
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.json()["data"]["model"], {
            "id": "yolo26n.pt", "name": "yolo26n.pt", "format": "pt", "task": "detect",
        })
        fake_model.predict.assert_called_once()


if __name__ == "__main__":
    unittest.main()
