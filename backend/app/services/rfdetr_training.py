import csv
import json
import math
import shutil
from pathlib import Path

from PIL import Image

from app.schemas.training import RFDETR_MODELS
from app.services.dataset_builder import IMAGE_SUFFIXES


BEST_CHECKPOINT = "checkpoint_best_total.pth"


def build_coco_snapshot(snapshot: Path, destination: Path) -> None:
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    categories = [
        {"id": item["trainingIndex"] + 1, "name": item["name"], "supercategory": ""}
        for item in manifest["classes"]
    ]
    category_ids = {item["id"] for item in categories}
    if not categories:
        raise ValueError("RF-DETR 数据集没有类别")

    for source_split, output_split in (("train", "train"), ("val", "valid"), ("test", "test")):
        source = snapshot / "images" / source_split
        if not source.is_dir() and source_split == "test":
            continue
        output = destination / output_split
        output.mkdir(parents=True, exist_ok=True)
        images, annotations = [], []
        for image_path in sorted(source.iterdir()):
            if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            with Image.open(image_path) as image:
                width, height = image.size
            image_id = len(images) + 1
            images.append({"id": image_id, "file_name": image_path.name, "width": width, "height": height})
            labels = snapshot / "labels" / source_split / (image_path.stem + ".txt")
            for line in labels.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                index, cx, cy, w, h = line.split()
                category_id = int(index) + 1
                cx, cy, w, h = map(float, (cx, cy, w, h))
                if category_id not in category_ids or not all(map(math.isfinite, (cx, cy, w, h))):
                    raise ValueError(f"检测标注无效：{labels.name}")
                left, top = max(0, (cx - w / 2) * width), max(0, (cy - h / 2) * height)
                right, bottom = min(width, (cx + w / 2) * width), min(height, (cy + h / 2) * height)
                box_width, box_height = right - left, bottom - top
                if box_width <= 0 or box_height <= 0:
                    raise ValueError(f"检测框面积无效：{labels.name}")
                annotations.append({
                    "id": len(annotations) + 1, "image_id": image_id, "category_id": category_id,
                    "bbox": [left, top, box_width, box_height], "area": box_width * box_height, "iscrowd": 0,
                })
            shutil.copy2(image_path, output / image_path.name)
        if not images and source_split != "test":
            raise ValueError(f"RF-DETR 数据集切分没有图片：{source_split}")
        (output / "_annotations.coco.json").write_text(
            json.dumps({"info": {}, "licenses": [], "images": images, "annotations": annotations, "categories": categories},
                       ensure_ascii=False),
            encoding="utf-8",
        )


def validation_rows(run_dir: Path) -> list[dict]:
    metrics_path = run_dir / "train" / "metrics.csv"
    if not metrics_path.is_file():
        return []
    names = {"val/mAP_50_95": "metrics/mAP50-95(B)", "val/mAP_50": "metrics/mAP50(B)",
             "val/precision": "metrics/precision(B)", "val/recall": "metrics/recall(B)"}
    by_epoch = {}
    with metrics_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row.get("epoch") or not row.get("val/mAP_50_95"):
                continue
            epoch = int(row["epoch"]) + 1
            by_epoch[epoch] = {"epoch": epoch, **{label: row[key] for key, label in names.items() if row.get(key)}}
    return list(by_epoch.values())


def train(root: Path, snapshot: Path, run_dir: Path, request) -> None:
    import rfdetr
    from rfdetr.assets.model_weights import validate_pretrain_weights

    variant, model_class = RFDETR_MODELS[request.model_path]
    weights = str(root / request.model_path)
    if not validate_pretrain_weights(weights):
        raise ValueError(f"RF-DETR {variant.title()} 权重缺失或校验失败，请重新准备官方权重")
    dataset = run_dir / "coco"
    build_coco_snapshot(snapshot, dataset)
    model = getattr(rfdetr, model_class)(pretrain_weights=weights)
    output = run_dir / "train"
    model.train(
        dataset_dir=str(dataset), output_dir=str(output), dataset_file="roboflow",
        epochs=request.epochs, batch_size=request.batch, grad_accum_steps=1,
        lr=request.lr0, seed=request.seed, num_workers=0, accelerator="gpu", devices=1,
        tensorboard=False, run_test=False,
    )
    if not (output / BEST_CHECKPOINT).is_file():
        raise RuntimeError("RF-DETR 未生成最佳权重")
    rows = validation_rows(run_dir)
    if not rows:
        raise RuntimeError("RF-DETR 未生成验证指标")
    with (run_dir / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(key for row in rows for key in row)))
        writer.writeheader()
        writer.writerows(rows)
