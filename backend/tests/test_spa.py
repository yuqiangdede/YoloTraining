import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class SpaFallbackTests(unittest.TestCase):
    def test_direct_navigation_returns_frontend_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "frontend" / "dist"
            dist.mkdir(parents=True)
            (dist / "index.html").write_text("<html><title>Studio SPA</title></html>", encoding="utf-8")
            app = create_app(root, start_worker=False)
            try:
                with TestClient(app) as client:
                    response = client.get("/models", headers={"Accept": "text/html"})
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("Studio SPA", response.text)
            finally:
                app.state.database.engine.dispose()


if __name__ == "__main__":
    unittest.main()
