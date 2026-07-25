import hashlib
import json
import math
import random
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Annotation, Asset, Dataset, DatasetCategory, DatasetVersion
from app.schemas.datasets import DatasetVersionCreate
from app.services.dataset_quality import run_quality_check


IMAGE_SUFFIXES = {".avif", ".bmp", ".dng", ".heic", ".heif", ".jpeg", ".jpg", ".jp2", ".mpo", ".png", ".tif", ".tiff", ".webp"}


class DatasetSplitError(ValueError):
    pass


def validate_snapshot_split(snapshot: Path, require_validation: bool = True) -> None:
    def image_count(split: str) -> int:
        directory = snapshot / "images" / split
        return sum(1 for path in directory.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES) if directory.is_dir() else 0

    missing = ["训练集" if image_count("train") == 0 else None, "验证集" if require_validation and image_count("val") == 0 else None]
    missing = [name for name in missing if name]
    if missing:
        raise DatasetSplitError(f"数据集切分无效：{'、'.join(missing)}没有图片。请补充素材后重新生成数据集版本。")


def _label_line(document: dict, shape: dict, class_index: int) -> str:
    points, task = shape.get("points", []), document["task"]
    if task == "detect":
        (x1, y1), (x2, y2) = points
        return f"{class_index} {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {abs(x2-x1):.6f} {abs(y2-y1):.6f}"
    if task in {"segment", "semantic"}:
        return f"{class_index} " + " ".join(f"{value:.6f}" for point in points for value in point)
    if task == "obb":
        (x1, y1), (x2, y2) = points; angle = math.radians(float(shape.get("rotation", 0)))
        cx, cy, half_width, half_height = (x1+x2)/2, (y1+y2)/2, abs(x2-x1)/2, abs(y2-y1)/2
        corners = [(cx + dx*math.cos(angle)-dy*math.sin(angle), cy + dx*math.sin(angle)+dy*math.cos(angle)) for dx, dy in [(-half_width,-half_height),(half_width,-half_height),(half_width,half_height),(-half_width,half_height)]]
        if any(value < 0 or value > 1 for corner in corners for value in corner): raise ValueError("旋转框角点超出图片范围")
        return f"{class_index} " + " ".join(f"{value:.6f}" for corner in corners for value in corner)
    visible = shape.get("visibility") or [2] * len(points); box_points = [point for point, value in zip(points, visible) if value > 0] or points
    min_x, max_x = min(point[0] for point in box_points), max(point[0] for point in box_points); min_y, max_y = min(point[1] for point in box_points), max(point[1] for point in box_points)
    values = [f"{(min_x+max_x)/2:.6f}", f"{(min_y+max_y)/2:.6f}", f"{max(max_x-min_x,.02):.6f}", f"{max(max_y-min_y,.02):.6f}"]
    for point, value in zip(points, visible): values.extend([f"{point[0]:.6f}", f"{point[1]:.6f}", str(value)])
    return f"{class_index} " + " ".join(values)


def _split_assets(assets: list[Asset], train_ratio: float, val_ratio: float, test_ratio: float, seed: int) -> dict[str, list[Asset]]:
    shuffled = sorted(assets, key=lambda item: item.sha256); random.Random(seed).shuffle(shuffled)
    ratios = {"train": train_ratio, "val": val_ratio, "test": test_ratio}; counts = {name: math.floor(len(shuffled)*ratio) for name, ratio in ratios.items()}
    for name in sorted(ratios, key=lambda name: (len(shuffled)*ratios[name]-counts[name], name), reverse=True)[:len(shuffled)-sum(counts.values())]: counts[name] += 1
    required = [name for name, ratio in ratios.items() if ratio > 0]
    if len(shuffled) >= len(required):
        for name in required:
            if not counts[name]: donor = max((candidate for candidate in counts if counts[candidate] > 1), key=counts.get); counts[donor] -= 1; counts[name] += 1
    return {"train": shuffled[:counts["train"]], "val": shuffled[counts["train"]:counts["train"]+counts["val"]], "test": shuffled[counts["train"]+counts["val"]:]}


def create_snapshot(session: Session, root: Path, dataset: Dataset, request: DatasetVersionCreate) -> DatasetVersion:
    assets = list(session.scalars(select(Asset).where(Asset.dataset_id == dataset.id, Asset.is_deleted.is_(False))))
    annotations = list(session.scalars(select(Annotation).where(Annotation.asset_id.in_([item.id for item in assets]))))
    by_asset = {item.asset_id: item for item in annotations}
    # REVIEWED remains backward-compatible, while COMPLETED is the normal gate.
    completed_annotations = [item for item in annotations if item.status == "COMPLETED"]
    for item in annotations:
        if item.status == "COMPLETED":
            item.status = "REVIEWED"
    if not assets: raise ValueError("数据集没有可用素材")
    if len(by_asset) != len(assets) or any(item.status != "REVIEWED" for item in annotations): raise ValueError("所有素材必须完成已审核标注")
    if any(item.task != dataset.task for item in annotations): raise ValueError("标注任务类型与数据集不一致")
    categories = list(session.scalars(select(DatasetCategory).where(DatasetCategory.dataset_id == dataset.id).order_by(DatasetCategory.created_at)))
    ids = {item.id for item in categories}
    quality = run_quality_check(session, dataset)
    if quality["status"] == "BLOCKED":
        raise ValueError("Dataset quality check is blocked")
    if any(shape["labelId"] not in ids for item in annotations for shape in json.loads(item.document_json)["shapes"]): raise ValueError("标注包含不属于数据集的类别")
    classes = [{"id": item.id, "name": item.name, "color": item.color, "trainingIndex": index} for index, item in enumerate(categories)]
    manifest = request.model_dump(mode="json", by_alias=True) | {"datasetId": dataset.id, "task": dataset.task, "classes": classes, "annotations": {item.asset_id: json.loads(item.document_json) for item in annotations}, "quality": quality}
    # Version labels are metadata; identical data, labels, split parameters and
    # seed must resolve to the same content address regardless of display name.
    hash_manifest = {key: value for key, value in manifest.items() if key != "name"}
    if isinstance(hash_manifest.get("quality"), dict):
        hash_manifest["quality"] = {key: value for key, value in hash_manifest["quality"].items() if key != "generatedAt"}
    content_hash = hashlib.sha256(json.dumps(hash_manifest, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    existing = session.scalar(select(DatasetVersion).where(DatasetVersion.content_hash == content_hash))
    if existing:
        for item in completed_annotations:
            item.status = "COMPLETED"
        return existing
    splits = _split_assets(assets, request.train_ratio, request.val_ratio, request.test_ratio, request.seed)
    if not splits["train"] or (request.val_ratio > 0 and not splits["val"]):
        missing = "训练集" if not splits["train"] else "验证集"
        raise DatasetSplitError(f"数据集切分无效：{missing}没有图片。当前素材数量不足以满足所选切分比例，请补充素材后重新生成数据集版本。")
    version_id, relative = str(uuid4()), Path("data") / "datasets" / str(uuid4())
    # Use the version ID as the directory name so metadata and filesystem are traceable.
    relative = Path("data") / "datasets" / version_id; snapshot = root / relative; class_ids = {item["id"]: item["trainingIndex"] for item in classes}
    for split, split_assets in splits.items():
        (snapshot / "images" / split).mkdir(parents=True, exist_ok=True); (snapshot / "labels" / split).mkdir(parents=True, exist_ok=True)
        for asset in split_assets:
            shutil.copy2(root / asset.storage_path, snapshot / "images" / split / asset.filename)
            document = json.loads(by_asset[asset.id].document_json)
            (snapshot / "labels" / split / f"{Path(asset.filename).stem}.txt").write_text("\n".join(_label_line(document, shape, class_ids[shape["labelId"]]) for shape in document["shapes"]), encoding="utf-8")
    names = "\n".join(f"  {item['trainingIndex']}: {item['name']}" for item in classes)
    yaml = f"path: {snapshot.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n{names}\n"
    if dataset.task == "pose":
        yaml += f"kpt_shape: [{dataset.keypoint_count}, 3]\n"
        if dataset.flip_idx_json: yaml += f"flip_idx: {json.loads(dataset.flip_idx_json)}\n"
    (snapshot / "data.yaml").write_text(yaml, encoding="utf-8"); (snapshot / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    version = DatasetVersion(id=version_id, dataset_id=dataset.id, name=request.name, task=dataset.task, snapshot_path=relative.as_posix(), content_hash=content_hash, manifest_json=json.dumps(manifest, ensure_ascii=False), asset_count=len(assets), parent_version_id=request.parent_version_id, quality_report_json=json.dumps(quality, ensure_ascii=False), source_json=json.dumps({"kind": "dataset", "datasetId": dataset.id}, ensure_ascii=False))
    for item in completed_annotations:
        item.status = "COMPLETED"
    session.add(version); session.commit(); return version
