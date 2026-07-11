import hashlib
import json
import math
import random
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Annotation, Asset, DatasetVersion
from app.schemas.datasets import DatasetCreate


def _label_line(document: dict, shape: dict, class_index: int) -> str:
    points = shape.get("points", [])
    task = document["task"]
    if task == "detect":
        (x1, y1), (x2, y2) = points
        return f"{class_index} {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {abs(x2-x1):.6f} {abs(y2-y1):.6f}"
    if task in {"segment", "semantic"}:
        flat = " ".join(f"{value:.6f}" for point in points for value in point)
        return f"{class_index} {flat}"
    if task == "obb":
        (x1, y1), (x2, y2) = points
        angle = math.radians(float(shape.get("rotation", 0)))
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        half_width, half_height = abs(x2 - x1) / 2, abs(y2 - y1) / 2
        corners = []
        for dx, dy in [(-half_width, -half_height), (half_width, -half_height), (half_width, half_height), (-half_width, half_height)]:
            corners.append((cx + dx * math.cos(angle) - dy * math.sin(angle), cy + dx * math.sin(angle) + dy * math.cos(angle)))
        if any(value < 0 or value > 1 for corner in corners for value in corner):
            raise ValueError("旋转框角点超出图片范围")
        flat = " ".join(f"{value:.6f}" for corner in corners for value in corner)
        return f"{class_index} {flat}"
    visible_points = [point for point, visible in zip(points, shape.get("visibility") or [2] * len(points)) if visible > 0]
    box_points = visible_points or points
    min_x, max_x = min(point[0] for point in box_points), max(point[0] for point in box_points)
    min_y, max_y = min(point[1] for point in box_points), max(point[1] for point in box_points)
    width, height = max(max_x - min_x, 0.02), max(max_y - min_y, 0.02)
    center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    values = [f"{center_x:.6f}", f"{center_y:.6f}", f"{width:.6f}", f"{height:.6f}"]
    visibility = shape.get("visibility") or [2] * len(points)
    for point, visible in zip(points, visibility):
        values.extend([f"{point[0]:.6f}", f"{point[1]:.6f}", str(visible)])
    return f"{class_index} " + " ".join(values)


def _split_assets(assets: list[Asset], train_ratio: float, val_ratio: float, test_ratio: float, seed: int) -> dict[str, list[Asset]]:
    shuffled = sorted(assets, key=lambda item: item.sha256)
    random.Random(seed).shuffle(shuffled)
    ratios = {"train": train_ratio, "val": val_ratio, "test": test_ratio}
    counts = {name: math.floor(len(shuffled) * ratio) for name, ratio in ratios.items()}
    remaining = len(shuffled) - sum(counts.values())
    fractions = sorted(ratios, key=lambda name: (len(shuffled) * ratios[name] - counts[name], name), reverse=True)
    for name in fractions[:remaining]:
        counts[name] += 1

    required = [name for name, ratio in ratios.items() if ratio > 0]
    if len(shuffled) >= len(required):
        for name in required:
            if counts[name] == 0:
                donor = max((candidate for candidate in counts if counts[candidate] > 1), key=counts.get)
                counts[donor] -= 1
                counts[name] += 1

    train_end = counts["train"]
    val_end = train_end + counts["val"]
    return {"train": shuffled[:train_end], "val": shuffled[train_end:val_end], "test": shuffled[val_end:]}


def create_snapshot(session: Session, root: Path, request: DatasetCreate) -> DatasetVersion:
    assets = list(session.scalars(select(Asset).where(Asset.id.in_(request.asset_ids), Asset.is_deleted.is_(False))))
    annotations = list(session.scalars(select(Annotation).where(Annotation.asset_id.in_(request.asset_ids))))
    annotation_by_asset = {item.asset_id: item for item in annotations}
    if len(assets) != len(set(request.asset_ids)):
        raise ValueError("素材不存在或已进入回收站")
    if any(asset.id not in annotation_by_asset for asset in assets):
        raise ValueError("所有素材必须先完成标注")
    if any(annotation_by_asset[asset.id].status != "REVIEWED" for asset in assets):
        raise ValueError("训练快照只接受已审核标注")
    if any(annotation_by_asset[asset.id].task != request.task for asset in assets):
        raise ValueError("标注任务类型与数据集不一致")

    manifest = request.model_dump(mode="json", by_alias=True)
    manifest["annotations"] = {
        item.asset_id: json.loads(item.document_json) for item in annotations
    }
    content = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    content_hash = hashlib.sha256(content).hexdigest()
    existing = session.scalar(select(DatasetVersion).where(DatasetVersion.content_hash == content_hash))
    if existing:
        return existing

    dataset_id = str(uuid4())
    relative = Path("data") / "datasets" / dataset_id
    snapshot = root / relative
    splits = _split_assets(assets, request.train_ratio, request.val_ratio, request.test_ratio, request.seed)
    class_ids = {item.id: index for index, item in enumerate(request.classes)}
    for split, split_assets in splits.items():
        (snapshot / "images" / split).mkdir(parents=True, exist_ok=True)
        (snapshot / "labels" / split).mkdir(parents=True, exist_ok=True)
        for asset in split_assets:
            source = root / asset.storage_path
            destination = snapshot / "images" / split / asset.filename
            shutil.copy2(source, destination)
            document = json.loads(annotation_by_asset[asset.id].document_json)
            lines = [_label_line(document, shape, class_ids[shape["labelId"]]) for shape in document["shapes"]]
            (snapshot / "labels" / split / f"{Path(asset.filename).stem}.txt").write_text("\n".join(lines), encoding="utf-8")
    names = "\n".join(f"  {index}: {item.name}" for index, item in enumerate(request.classes))
    yaml = f"path: {snapshot.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n{names}\n"
    if request.task == "pose":
        yaml += f"kpt_shape: [{request.keypoint_count}, 3]\n"
        if request.flip_idx:
            yaml += f"flip_idx: {request.flip_idx}\n"
    (snapshot / "data.yaml").write_text(yaml, encoding="utf-8")
    (snapshot / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    version = DatasetVersion(
        id=dataset_id, name=request.name, task=request.task, snapshot_path=relative.as_posix(),
        content_hash=content_hash, manifest_json=json.dumps(manifest, ensure_ascii=False), asset_count=len(assets),
    )
    session.add(version)
    session.commit()
    return version
