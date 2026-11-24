import json

import pytest
from PIL import Image
from pydantic import ValidationError

from app.schemas.training import RFDETR_MODELS, RFDETR_WEIGHTS, TrainRequest
from app.services.rfdetr_training import build_coco_snapshot, validation_rows


def test_rfdetr_request_uses_engine_defaults_and_rejects_yolo_options():
    payload = {"engine": "rfdetr", "name": "nano", "datasetVersionId": "snapshot",
               "task": "detect", "modelPath": RFDETR_WEIGHTS}
    request = TrainRequest.model_validate(payload)
    assert request.batch == 2
    assert request.lr0 == 0.0001
    for path in RFDETR_MODELS:
        assert TrainRequest.model_validate(payload | {"modelPath": path}).model_path == path
    for options in ({"task": "segment"}, {"imgsz": 640}, {"batch": 0}, {"resume": True},
                    {"modelPath": "models/pretrained/rfdetr/rf-detr-large.pth"}):
        with pytest.raises(ValidationError):
            TrainRequest.model_validate(payload | options)


def test_coco_conversion_preserves_snapshot_splits_and_negative_images(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(json.dumps({
        "classes": [{"trainingIndex": 0, "name": "方块"}, {"trainingIndex": 1, "name": "圆形"}],
    }), encoding="utf-8")
    for split, names in (("train", ("object", "empty")), ("val", ("validation",))):
        (snapshot / "images" / split).mkdir(parents=True)
        (snapshot / "labels" / split).mkdir(parents=True)
        for name in names:
            Image.new("RGB", (200, 100)).save(snapshot / "images" / split / f"{name}.png")
            (snapshot / "labels" / split / f"{name}.txt").write_text(
                "" if name == "empty" else "1 0.5 0.5 0.5 0.5", encoding="utf-8",
            )
    before = {path: path.read_bytes() for path in snapshot.rglob("*") if path.is_file()}
    output = tmp_path / "coco"
    build_coco_snapshot(snapshot, output)
    train = json.loads((output / "train" / "_annotations.coco.json").read_text(encoding="utf-8"))
    validation = json.loads((output / "valid" / "_annotations.coco.json").read_text(encoding="utf-8"))
    assert [image["file_name"] for image in train["images"]] == ["empty.png", "object.png"]
    assert train["annotations"] == [
        {"id": 1, "image_id": 2, "category_id": 2, "bbox": [50, 25, 100, 50], "area": 5000, "iscrowd": 0},
    ]
    assert [image["file_name"] for image in validation["images"]] == ["validation.png"]
    assert train["categories"] == validation["categories"]
    assert {path: path.read_bytes() for path in snapshot.rglob("*") if path.is_file()} == before


def test_rfdetr_metrics_select_validation_rows_and_use_one_based_epochs(tmp_path):
    output = tmp_path / "train"
    output.mkdir()
    (output / "metrics.csv").write_text(
        "epoch,step,val/mAP_50_95,val/mAP_50\n0,1,,\n0,1,0,0.2\n1,2,0.1,0.3\n",
        encoding="utf-8",
    )
    assert validation_rows(tmp_path) == [
        {"epoch": 1, "metrics/mAP50-95(B)": "0", "metrics/mAP50(B)": "0.2"},
        {"epoch": 2, "metrics/mAP50-95(B)": "0.1", "metrics/mAP50(B)": "0.3"},
    ]
