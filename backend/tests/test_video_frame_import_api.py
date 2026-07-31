import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app


class VideoFrameImportApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.client = TestClient(create_app(self.root, start_worker=False))
        self.dataset = self.client.post("/api/v1/datasets", json={
            "name": "video", "task": "detect", "categories": [{"name": "car"}],
        }).json()["data"]

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def test_extracts_frames_at_configured_step(self) -> None:
        source = self.root / "source.avi"
        writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 10, (32, 24))
        for index in range(6):
            writer.write(np.full((24, 32, 3), index * 30, dtype=np.uint8))
        writer.release()
        with source.open("rb") as stream:
            response = self.client.post(
                f"/api/v1/datasets/{self.dataset['id']}/video-frames?frameStep=2",
                files={"video": ("camera.avi", stream, "video/x-msvideo")},
            )
        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(len(payload["data"]), 3)
        self.assertEqual(payload["frameStep"], 2)
        self.assertTrue((self.root / payload["sourcePath"]).is_file())
        self.assertEqual(payload["data"][0]["tags"], ["video:camera.avi", "frame:0"])


if __name__ == "__main__":
    unittest.main()
