import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class CategoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(); self.client = TestClient(create_app(Path(self.temp.name), start_worker=False))

    def tearDown(self) -> None:
        self.client.close(); self.client.app.state.database.engine.dispose(); self.temp.cleanup()

    def test_categories_are_private_to_a_dataset(self) -> None:
        dataset = self.client.post('/api/v1/datasets', json={'name': 'one', 'task': 'detect', 'categories': [{'name': 'car'}]}).json()['data']
        created = self.client.post(f"/api/v1/datasets/{dataset['id']}/categories", json={'name': 'bus'})
        self.assertEqual(created.status_code, 201)
        self.assertEqual([item['name'] for item in self.client.get(f"/api/v1/datasets/{dataset['id']}/categories").json()['data']], ['car', 'bus'])

    def test_renaming_and_deleting_category_keeps_ids_and_clears_shapes(self) -> None:
        dataset = self.client.post('/api/v1/datasets', json={'name': 'editable', 'task': 'detect', 'categories': [{'name': 'car'}]}).json()['data']
        from io import BytesIO
        from PIL import Image
        image = BytesIO(); Image.new('RGB', (16, 16), '#fff').save(image, format='PNG')
        asset = self.client.post(f"/api/v1/datasets/{dataset['id']}/assets", files={'files': ('a.png', image.getvalue(), 'image/png')}).json()['data'][0]
        category_id = dataset['categories'][0]['id']
        self.client.put(f"/api/v1/datasets/{dataset['id']}/assets/{asset['id']}/annotation", json={'assetId': asset['id'], 'task': 'detect', 'imageWidth': 16, 'imageHeight': 16, 'status': 'REVIEWED', 'shapes': [{'id': 'shape', 'labelId': category_id, 'kind': 'rectangle', 'points': [[.1, .1], [.5, .5]]}]})
        renamed = self.client.patch(f"/api/v1/datasets/{dataset['id']}/categories/{category_id}", json={'name': 'vehicle'})
        self.assertEqual(renamed.status_code, 200); self.assertEqual(renamed.json()['data']['id'], category_id)
        deleted = self.client.delete(f"/api/v1/datasets/{dataset['id']}/categories/{category_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/datasets/{dataset['id']}/assets/{asset['id']}/annotation").json()['data']['shapes'], [])
