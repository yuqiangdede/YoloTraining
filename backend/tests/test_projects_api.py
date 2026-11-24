import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class ProjectsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp.name), start_worker=False))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def test_default_project_owns_unscoped_datasets(self) -> None:
        created = self.client.post("/api/v1/datasets", json={
            "name": "roads", "task": "detect", "categories": [{"name": "car"}],
        })
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["data"]["projectId"], "default")
        project = self.client.get("/api/v1/projects/default").json()["data"]
        self.assertEqual(project["datasetCount"], 1)

    def test_project_filters_its_datasets(self) -> None:
        project = self.client.post("/api/v1/projects", json={
            "name": "高速公路", "description": "车辆检测",
        }).json()["data"]
        created = self.client.post("/api/v1/datasets", json={
            "projectId": project["id"], "name": "daylight", "task": "detect",
            "categories": [{"name": "car"}],
        })
        self.assertEqual(created.status_code, 201)
        listed = self.client.get(f"/api/v1/datasets?project_id={project['id']}").json()["data"]
        self.assertEqual([item["name"] for item in listed], ["daylight"])

    def test_rejects_unknown_project(self) -> None:
        response = self.client.post("/api/v1/datasets", json={
            "projectId": "missing", "name": "orphan", "task": "detect",
            "categories": [{"name": "car"}],
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "PROJECT_NOT_FOUND")

    def test_delete_empty_project(self) -> None:
        project = self.client.post("/api/v1/projects", json={"name": "待删除"}).json()["data"]
        url = f"/api/v1/projects/{project['id']}"
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_delete_preserves_default_and_projects_with_datasets(self) -> None:
        self.assertEqual(self.client.delete("/api/v1/projects/default").status_code, 409)
        project = self.client.post("/api/v1/projects", json={"name": "保留"}).json()["data"]
        project_id = project["id"]
        created = self.client.post("/api/v1/datasets", json={
            "projectId": project_id, "name": "dataset", "task": "detect", "categories": [{"name": "car"}],
        })
        self.assertEqual(created.status_code, 201)
        response = self.client.delete(f"/api/v1/projects/{project_id}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "PROJECT_NOT_EMPTY")
        self.assertEqual(self.client.get(f"/api/v1/projects/{project_id}").json()["data"]["datasetCount"], 1)


if __name__ == "__main__":
    unittest.main()
