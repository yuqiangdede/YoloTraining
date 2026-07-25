import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class VideoInferenceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.client = TestClient(create_app(self.root, start_worker=False))
        model_dir = self.root / "models" / "pretrained"
        model_dir.mkdir(parents=True)
        (model_dir / "yolo26n.pt").write_bytes(b"model")

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def test_rejects_invalid_video_and_confidence(self) -> None:
        invalid = self.client.post(
            "/api/v1/models/video-jobs", data={"modelId": "pretrained:yolo26n.pt", "confidence": "0.25"},
            files={"video": ("test.txt", b"not-video", "text/plain")},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["error"]["code"], "INVALID_VIDEO")

        invalid_confidence = self.client.post(
            "/api/v1/models/video-jobs", data={"modelId": "pretrained:yolo26n.pt", "confidence": "1.2"},
            files={"video": ("test.mp4", b"video", "video/mp4")},
        )
        self.assertEqual(invalid_confidence.status_code, 422)
        self.assertEqual(invalid_confidence.json()["error"]["code"], "INVALID_CONFIDENCE")

    def test_queues_pretrained_video_job_and_can_cancel_it(self) -> None:
        response = self.client.post(
            "/api/v1/models/video-jobs", data={"modelId": "pretrained:yolo26n.pt", "confidence": "0.4", "format": "pt"},
            files={"video": ("test.mp4", b"video", "video/mp4")},
        )
        self.assertEqual(response.status_code, 201)
        job = response.json()
        self.assertEqual(job["status"], "QUEUED")
        self.assertEqual(job["modelId"], "pretrained:yolo26n.pt")
        self.assertEqual(job["params"]["confidence"], 0.4)
        self.assertTrue((self.root / "runs" / "video-inference" / job["id"] / "input.mp4").is_file())

        cancelled = self.client.post(f"/api/v1/models/video-jobs/{job['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], "CANCELLED")
        self.assertEqual(self.client.get(f"/api/v1/models/video-jobs/{job['id']}").json()["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
