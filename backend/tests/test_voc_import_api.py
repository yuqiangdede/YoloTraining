import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.services.voc_importer import VocImportError, parse_voc_to_coco


def image_bytes(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buffer, format="JPEG")
    return buffer.getvalue()


class VocImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "studio"
        self.source = Path(self.temp.name) / "SeaShips(7000)"
        (self.source / "JPEGImages").mkdir(parents=True)
        (self.source / "Annotations").mkdir()
        (self.source / "ImageSets" / "Main").mkdir(parents=True)
        self.client = TestClient(create_app(self.root, start_worker=False))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.database.engine.dispose()
        self.temp.cleanup()

    def add_sample(self, index: int, category: str = "ore carrier", malformed: bool = False) -> None:
        filename = f"{index:06d}.jpg"
        (self.source / "JPEGImages" / filename).write_bytes(image_bytes(f"#{index:02x}1000"))
        folder = "<folder>JPEGImages/folder>" if malformed else "<folder>JPEGImages</folder>"
        xml = f"""<annotation>
  {folder}
  <filename>{filename}</filename>
  <size><width>64</width><height>48</height><depth>3</depth></size>
  <object><name>{category}</name><bndbox><xmin>8</xmin><ymin>6</ymin><xmax>40</xmax><ymax>30</ymax></bndbox></object>
</annotation>"""
        (self.source / "Annotations" / f"{index:06d}.xml").write_text(xml, encoding="utf-8")

    def test_converts_voc_to_coco_and_repairs_known_folder_tag(self) -> None:
        self.add_sample(1, "ore carrier", malformed=True)
        self.add_sample(2, "bulk cargo carrier")

        parsed = parse_voc_to_coco(self.source)

        self.assertEqual([item["name"] for item in parsed.payload["categories"]], ["bulk cargo carrier", "ore carrier"])
        self.assertEqual(len(parsed.payload["images"]), 2)
        self.assertEqual(len(parsed.payload["annotations"]), 2)
        self.assertEqual(parsed.payload["annotations"][0]["bbox"], [8.0, 6.0, 32.0, 24.0])
        self.assertEqual(parsed.repaired_files, ["000001.xml"])

    def test_import_creates_reviewed_annotations_and_random_snapshot(self) -> None:
        for index in range(1, 5):
            self.add_sample(index, "ore carrier" if index % 2 else "fishing boat")
        (self.source / "ImageSets" / "Main" / "train.txt").write_text("000001\n000002\n", encoding="utf-8")
        (self.source / "ImageSets" / "Main" / "val.txt").write_text("000003\n000004\n", encoding="utf-8")

        response = self.client.post("/api/v1/datasets/imports/voc", json={
            "sourcePath": str(self.source), "name": "SeaShips", "trainRatio": 0.75, "valRatio": 0.25, "seed": 7,
        })

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()["data"]
        self.assertEqual(body["report"]["importedImages"], 4)
        self.assertEqual(body["report"]["annotationCount"], 4)
        self.assertEqual(body["report"]["split"], {"train": 3, "val": 1, "test": 0})
        self.assertEqual(body["report"]["categories"], ["fishing boat", "ore carrier"])

        version_dir = self.root / body["version"]["snapshotPath"]
        self.assertEqual(len(list((version_dir / "images" / "train").iterdir())), 3)
        self.assertEqual(len(list((version_dir / "images" / "val").iterdir())), 1)
        assets = self.client.get(f"/api/v1/datasets/{body['dataset']['id']}/assets?pageSize=100").json()
        self.assertEqual(len(assets["data"]), 4)
        self.assertTrue(all(item["annotationStatus"] == "REVIEWED" for item in assets["data"]))

    def test_import_failure_does_not_leave_dataset_or_copied_assets(self) -> None:
        self.add_sample(1)
        (self.source / "Annotations" / "000002.xml").write_text(
            "<annotation><filename>000002.jpg</filename><size><width>64</width><height>48</height></size></annotation>",
            encoding="utf-8",
        )

        response = self.client.post("/api/v1/datasets/imports/voc", json={"sourcePath": str(self.source), "name": "broken"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "MISSING_IMAGE")
        self.assertEqual(self.client.get("/api/v1/datasets").json()["data"], [])
        assets_root = self.root / "uploads" / "assets"
        self.assertFalse(assets_root.exists() and any(assets_root.rglob("*")))

    def test_rejects_xml_external_entity(self) -> None:
        self.add_sample(1)
        xml = (self.source / "Annotations" / "000001.xml").read_text(encoding="utf-8")
        (self.source / "Annotations" / "000001.xml").write_text(
            '<!DOCTYPE annotation [<!ENTITY xxe SYSTEM "file:///secret">]>' + xml,
            encoding="utf-8",
        )

        with self.assertRaises(VocImportError) as context:
            parse_voc_to_coco(self.source)
        self.assertEqual(context.exception.code, "INVALID_VOC_ANNOTATION")


if __name__ == "__main__":
    unittest.main()
