import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app


def image_bytes(color: str = "#d97706") -> bytes:
    buffer = io.BytesIO(); Image.new("RGB", (64, 48), color).save(buffer, format="PNG"); return buffer.getvalue()


class AssetDatasetApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); self.client = TestClient(create_app(self.root, start_worker=False))

    def tearDown(self) -> None:
        self.client.close(); self.client.app.state.database.engine.dispose(); self.temp.cleanup()

    def workspace(self) -> dict:
        return self.client.post('/api/v1/datasets', json={'name': 'roads', 'task': 'detect', 'categories': [{'name': 'car'}]}).json()['data']

    def test_annotation_then_immutable_dataset_snapshot(self) -> None:
        dataset = self.workspace(); category = dataset['categories'][0]
        uploaded = self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files=[('files', ('first.png', image_bytes('#d97706'), 'image/png')), ('files', ('second.png', image_bytes('#2563eb'), 'image/png'))]).json()['data']
        for index, asset in enumerate(uploaded):
            annotation = {'assetId': asset['id'], 'task': 'detect', 'imageWidth': 64, 'imageHeight': 48, 'status': 'REVIEWED', 'shapes': [{'id': f'shape-{index}', 'labelId': category['id'], 'kind': 'rectangle', 'points': [[.1, .1], [.8, .8]]}]}
            self.assertEqual(self.client.put(f"/api/v1/datasets/{dataset['id']}/assets/{asset['id']}/annotation", json=annotation).status_code, 200)
        snapshot = self.client.post(f"/api/v1/datasets/{dataset['id']}/versions", json={'name': 'roads-v1', 'trainRatio': .8, 'valRatio': .2, 'testRatio': 0, 'seed': 7})
        self.assertEqual(snapshot.status_code, 201); body = snapshot.json(); snapshot_dir = self.root / body['snapshotPath']
        self.assertTrue((snapshot_dir / 'data.yaml').exists()); self.assertEqual(len(list((snapshot_dir / 'images' / 'train').iterdir())), 1); self.assertEqual(len(list((snapshot_dir / 'images' / 'val').iterdir())), 1)

    def test_snapshot_rejects_empty_validation_split(self) -> None:
        dataset = self.workspace(); category = dataset['categories'][0]
        asset = self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={'files': ('sample.png', image_bytes(), 'image/png')}).json()['data'][0]
        annotation = {'assetId': asset['id'], 'task': 'detect', 'imageWidth': 64, 'imageHeight': 48, 'status': 'REVIEWED', 'shapes': [{'id': 'shape-1', 'labelId': category['id'], 'kind': 'rectangle', 'points': [[.1, .1], [.8, .8]]}]}
        self.assertEqual(self.client.put(f"/api/v1/datasets/{dataset['id']}/assets/{asset['id']}/annotation", json=annotation).status_code, 200)
        response = self.client.post(f"/api/v1/datasets/{dataset['id']}/versions", json={'name': 'single-image', 'trainRatio': .8, 'valRatio': .2, 'testRatio': 0, 'seed': 7})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'INVALID_DATASET_SPLIT')

    def test_assets_cannot_be_read_from_another_workspace(self) -> None:
        first = self.workspace(); second = self.client.post('/api/v1/datasets', json={'name': 'other', 'task': 'detect', 'categories': [{'name': 'person'}]}).json()['data']
        asset_id = self.client.post(f"/api/v1/datasets/{first['id']}/assets", files={'files': ('sample.png', image_bytes(), 'image/png')}).json()['data'][0]['id']
        self.assertEqual(self.client.get(f"/api/v1/datasets/{second['id']}/assets/{asset_id}/annotation").status_code, 404)

    def test_manual_annotation_preserves_draft_status(self) -> None:
        dataset = self.workspace(); category = dataset['categories'][0]
        asset = self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={'files': ('sample.png', image_bytes(), 'image/png')}).json()['data'][0]
        response = self.client.put(f"/api/v1/datasets/{dataset['id']}/assets/{asset['id']}/annotation", json={'assetId': asset['id'], 'task': 'detect', 'imageWidth': 64, 'imageHeight': 48, 'status': 'DRAFT', 'shapes': [{'id': 'shape-1', 'labelId': category['id'], 'kind': 'rectangle', 'points': [[.1, .1], [.8, .8]]}]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'DRAFT')

    def test_two_assets_keep_a_validation_sample_when_validation_is_enabled(self) -> None:
        from types import SimpleNamespace
        from app.services.dataset_builder import _split_assets
        splits = _split_assets([SimpleNamespace(sha256='a'), SimpleNamespace(sha256='b')], .8, .2, 0, 7)
        self.assertEqual((len(splits['train']), len(splits['val'])), (1, 1))

    def test_deletes_an_old_dataset_version_and_finished_training_history(self) -> None:
        from app.models import DatasetVersion, TrainingJob
        dataset = self.workspace()
        snapshot = self.root / "data" / "datasets" / "old-version"
        snapshot.mkdir(parents=True)
        run_dir = self.root / "runs" / "old-job"
        run_dir.mkdir(parents=True)
        with self.client.app.state.database.session() as session:
            session.add(DatasetVersion(id="old-version", dataset_id=dataset["id"], name="old", task="detect", snapshot_path="data/datasets/old-version", content_hash="d" * 64, manifest_json="{}", asset_count=0))
            session.add(TrainingJob(id="old-job", name="old job", dataset_version_id="old-version", task="detect", model_path="models/pretrained/yolo26n.pt", run_path="runs/old-job", status="SUCCEEDED", params_json="{}"))
            session.commit()

        response = self.client.delete(f"/api/v1/datasets/{dataset['id']}/versions/old-version")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(snapshot.exists())
        self.assertFalse(run_dir.exists())
        self.assertEqual(self.client.get(f"/api/v1/training-jobs/old-job").status_code, 404)
