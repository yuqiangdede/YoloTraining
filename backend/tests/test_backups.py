import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.backups import BackupService


class BackupServiceTests(unittest.TestCase):
    def test_creates_portable_backup_without_venv_or_prior_backups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "uploads" / "assets").mkdir(parents=True)
            (root / "models" / "pretrained").mkdir(parents=True)
            (root / "runs").mkdir()
            (root / ".venv").mkdir()
            (root / "backups").mkdir()
            (root / "data" / "studio.db").write_bytes(b"database")
            (root / "uploads" / "assets" / "sample.jpg").write_bytes(b"image")
            (root / "models" / "pretrained" / "model.pt").write_bytes(b"model")
            (root / ".venv" / "ignore.txt").write_text("ignore", encoding="utf-8")
            (root / "backups" / "old.zip").write_bytes(b"old")

            record = BackupService(root).create("before-upgrade")

            self.assertEqual(record.label, "before-upgrade")
            self.assertTrue((root / record.path).is_file())
            with zipfile.ZipFile(root / record.path) as archive:
                names = archive.namelist()
                self.assertIn("backup-manifest.json", names)
                self.assertIn("data/studio.db", names)
                self.assertIn("uploads/assets/sample.jpg", names)
                self.assertIn("models/pretrained/model.pt", names)
                self.assertFalse(any(name.startswith(".venv/") for name in names))
                self.assertFalse(any(name.startswith("backups/") for name in names))

    def test_backup_api_creates_lists_and_downloads_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(root, start_worker=False)
            try:
                with TestClient(app) as client:
                    created = client.post("/api/v1/backups", json={"label": "manual"})
                    self.assertEqual(created.status_code, 200)
                    filename = Path(created.json()["path"]).name
                    listed = client.get("/api/v1/backups")
                    self.assertEqual(len(listed.json()["data"]), 1)
                    downloaded = client.get(f"/api/v1/backups/{filename}/download")
                    self.assertEqual(downloaded.status_code, 200)
                    self.assertEqual(downloaded.headers["content-type"], "application/zip")
            finally:
                app.state.database.engine.dispose()


if __name__ == "__main__":
    unittest.main()
