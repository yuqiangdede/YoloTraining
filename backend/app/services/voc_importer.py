from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Annotation, Asset, Dataset, DatasetCategory, DatasetVersion
from app.services.dataset_builder import _split_assets, create_snapshot
from app.schemas.datasets import DatasetVersionCreate


VOC_IMAGE_SUFFIXES = {".avif", ".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
MAX_XML_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 50 * 1024 * 1024
_KNOWN_FOLDER_TAG_ERROR = re.compile(rb"(<folder>[^<]*)/folder>", re.IGNORECASE)


class VocImportError(ValueError):
    def __init__(self, code: str, message: str, details: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class CocoImport:
    payload: dict
    source_files: dict[int, Path]
    repaired_files: list[str]


def _safe_child(root: Path, child: Path, label: str) -> Path:
    if child.is_symlink():
        raise VocImportError("INVALID_VOC_STRUCTURE", f"{label} 不能是符号链接")
    resolved = child.resolve()
    if resolved != root and root not in resolved.parents:
        raise VocImportError("INVALID_VOC_STRUCTURE", f"{label} 必须位于源数据目录内")
    return resolved


def _text(parent: ET.Element, tag: str, filename: str, required: bool = True) -> str:
    value = parent.findtext(tag)
    if value is None or not value.strip():
        if required:
            raise VocImportError("INVALID_VOC_ANNOTATION", f"{filename} 缺少 {tag} 字段")
        return ""
    return value.strip()


def _number(parent: ET.Element, tag: str, filename: str) -> float:
    raw = _text(parent, tag, filename)
    try:
        value = float(raw)
    except ValueError as error:
        raise VocImportError("INVALID_VOC_ANNOTATION", f"{filename} 的 {tag} 不是有效数字") from error
    if not math.isfinite(value):
        raise VocImportError("INVALID_VOC_ANNOTATION", f"{filename} 的 {tag} 不是有限数字")
    return value


def _parse_xml(path: Path) -> tuple[ET.Element, bool]:
    if path.is_symlink():
        raise VocImportError("INVALID_VOC_STRUCTURE", f"标注文件不能是符号链接：{path.name}")
    raw = path.read_bytes()
    if len(raw) > MAX_XML_BYTES:
        raise VocImportError("INVALID_VOC_ANNOTATION", f"标注文件过大：{path.name}")
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)", raw, re.IGNORECASE):
        raise VocImportError("INVALID_VOC_ANNOTATION", f"标注文件禁止包含 DTD 或外部实体：{path.name}")
    repaired = _KNOWN_FOLDER_TAG_ERROR.search(raw) is not None
    if repaired:
        raw = _KNOWN_FOLDER_TAG_ERROR.sub(rb"\1</folder>", raw, count=1)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise VocImportError("INVALID_VOC_ANNOTATION", f"无法解析标注文件：{path.name}") from error
    if root.tag != "annotation":
        raise VocImportError("INVALID_VOC_ANNOTATION", f"标注文件根节点必须是 annotation：{path.name}")
    return root, repaired


def _validate_filename(value: str, filename: str) -> str:
    candidate = PureWindowsPath(value)
    if candidate.name != value or candidate.is_absolute() or candidate.drive:
        raise VocImportError("INVALID_VOC_ANNOTATION", f"{filename} 的图片文件名不合法")
    return candidate.name


def parse_voc_to_coco(source_path: str | Path) -> CocoImport:
    source = Path(source_path).expanduser()
    try:
        source = source.resolve(strict=True)
    except OSError as error:
        raise VocImportError("INVALID_IMPORT_PATH", "源数据目录不存在或无法访问") from error
    if not source.is_dir() or source.is_symlink():
        raise VocImportError("INVALID_IMPORT_PATH", "sourcePath 必须是本机目录")

    image_dir = _safe_child(source, source / "JPEGImages", "JPEGImages")
    annotation_dir = _safe_child(source, source / "Annotations", "Annotations")
    if not image_dir.is_dir() or not annotation_dir.is_dir():
        raise VocImportError("INVALID_VOC_STRUCTURE", "源目录必须同时包含 JPEGImages 和 Annotations")

    image_paths = sorted(
        (path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in VOC_IMAGE_SUFFIXES),
        key=lambda path: path.name.casefold(),
    )
    xml_paths = sorted(annotation_dir.glob("*.xml"), key=lambda path: path.name.casefold())
    if not image_paths or not xml_paths:
        raise VocImportError("INVALID_VOC_STRUCTURE", "JPEGImages 和 Annotations 不能为空")
    if any(path.is_symlink() for path in image_paths):
        raise VocImportError("INVALID_VOC_STRUCTURE", "图片文件不能是符号链接")

    images_by_name = {path.name.casefold(): path for path in image_paths}
    if len(images_by_name) != len(image_paths):
        raise VocImportError("INVALID_VOC_STRUCTURE", "图片文件名不允许大小写重复")
    seen_images: set[str] = set()
    categories_by_name: dict[str, str] = {}
    coco_images: list[dict] = []
    coco_annotations: list[dict] = []
    source_files: dict[int, Path] = {}
    repaired_files: list[str] = []
    annotation_id = 1

    for image_id, xml_path in enumerate(xml_paths, start=1):
        root, repaired = _parse_xml(xml_path)
        if repaired:
            repaired_files.append(xml_path.name)
        image_name = _validate_filename(_text(root, "filename", xml_path.name), xml_path.name)
        image = images_by_name.get(image_name.casefold())
        if image is None:
            raise VocImportError("MISSING_IMAGE", f"标注文件找不到对应图片：{image_name}", [xml_path.name])
        image_key = image.name.casefold()
        if image_key in seen_images:
            raise VocImportError("INVALID_VOC_STRUCTURE", f"图片被多个 XML 重复引用：{image.name}")
        seen_images.add(image_key)

        if image.stat().st_size > MAX_IMAGE_BYTES:
            raise VocImportError("INVALID_IMAGE", f"图片文件过大：{image.name}")
        try:
            with Image.open(image) as opened:
                opened.verify()
            with Image.open(image) as opened:
                width, height = opened.size
        except (UnidentifiedImageError, OSError) as error:
            raise VocImportError("INVALID_IMAGE", f"图片文件无效：{image.name}") from error
        xml_size = root.find("size")
        if xml_size is None:
            raise VocImportError("INVALID_VOC_ANNOTATION", f"{xml_path.name} 缺少 size 字段")
        declared_width_value = _number(xml_size, "width", xml_path.name)
        declared_height_value = _number(xml_size, "height", xml_path.name)
        if not declared_width_value.is_integer() or not declared_height_value.is_integer():
            raise VocImportError("INVALID_VOC_ANNOTATION", f"{xml_path.name} 的图片尺寸必须是整数")
        declared_width = int(declared_width_value)
        declared_height = int(declared_height_value)
        if declared_width != width or declared_height != height:
            raise VocImportError("IMAGE_SIZE_MISMATCH", f"{xml_path.name} 的尺寸与图片不一致")

        coco_images.append({"id": image_id, "file_name": image.name, "width": width, "height": height})
        source_files[image_id] = image
        for object_node in root.findall("object"):
            category_name = _text(object_node, "name", xml_path.name)
            if len(category_name) > 100:
                raise VocImportError("INVALID_VOC_ANNOTATION", f"{xml_path.name} 的类别名称过长")
            category_key = category_name.casefold()
            categories_by_name.setdefault(category_key, category_name)
            box = object_node.find("bndbox")
            if box is None:
                raise VocImportError("INVALID_VOC_ANNOTATION", f"{xml_path.name} 的目标缺少 bndbox")
            xmin = _number(box, "xmin", xml_path.name)
            ymin = _number(box, "ymin", xml_path.name)
            xmax = _number(box, "xmax", xml_path.name)
            ymax = _number(box, "ymax", xml_path.name)
            if xmin < 0 or ymin < 0 or xmax <= xmin or ymax <= ymin or xmax > width or ymax > height:
                raise VocImportError("INVALID_VOC_ANNOTATION", f"{xml_path.name} 存在超出图片范围的目标框")
            coco_annotations.append({
                "id": annotation_id,
                "image_id": image_id,
                "category_name": category_key,
                "bbox": [xmin, ymin, xmax - xmin, ymax - ymin],
                "area": (xmax - xmin) * (ymax - ymin),
                "iscrowd": 0,
            })
            annotation_id += 1

    missing_xml = [path.name for path in image_paths if path.name.casefold() not in seen_images]
    if missing_xml:
        raise VocImportError("MISSING_ANNOTATION", "存在没有对应 XML 的图片", missing_xml[:20])

    ordered_categories = [categories_by_name[key] for key in sorted(categories_by_name, key=lambda item: (item, categories_by_name[item]))]
    category_ids = {name.casefold(): index + 1 for index, name in enumerate(ordered_categories)}
    for annotation in coco_annotations:
        annotation["category_id"] = category_ids[annotation.pop("category_name")]
    coco = {
        "info": {"description": "Imported Pascal VOC dataset"},
        "licenses": [],
        "images": coco_images,
        "annotations": coco_annotations,
        "categories": [{"id": category_ids[name.casefold()], "name": name, "supercategory": ""} for name in ordered_categories],
    }
    return CocoImport(coco, source_files, repaired_files)


def _cleanup_import_records(
    session: Session,
    dataset_id: str,
    asset_ids: list[str],
    root: Path,
    copied: list[Path],
    snapshot_before: set[Path] | None = None,
) -> None:
    session.rollback()
    if asset_ids:
        session.execute(delete(Annotation).where(Annotation.asset_id.in_(asset_ids)))
        session.execute(delete(Asset).where(Asset.id.in_(asset_ids)))
    session.execute(delete(DatasetCategory).where(DatasetCategory.dataset_id == dataset_id))
    session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id))
    session.execute(delete(Dataset).where(Dataset.id == dataset_id))
    session.commit()
    for path in copied:
        path.unlink(missing_ok=True)
    shutil.rmtree(root / "uploads" / "assets" / dataset_id, ignore_errors=True)
    if snapshot_before is not None:
        snapshot_root = root / "data" / "datasets"
        if snapshot_root.is_dir():
            for candidate in snapshot_root.iterdir():
                if candidate not in snapshot_before:
                    shutil.rmtree(candidate, ignore_errors=True)


def import_voc_dataset(
    session: Session,
    project_root: Path,
    source_path: str | Path,
    name: str,
    train_ratio: float,
    val_ratio: float,
    seed: int,
) -> tuple[Dataset, DatasetVersion, dict]:
    if session.scalar(select(Dataset).where(Dataset.name == name)):
        raise VocImportError("DATASET_NAME_EXISTS", "数据集名称已存在")
    parsed = parse_voc_to_coco(source_path)
    dataset_id = str(uuid4())
    dataset = Dataset(id=dataset_id, name=name, task="detect")
    copied: list[Path] = []
    asset_ids: list[str] = []
    snapshot_root = project_root / "data" / "datasets"
    snapshot_before = set(snapshot_root.iterdir()) if snapshot_root.is_dir() else set()
    try:
        session.add(dataset)
        category_rows: dict[int, DatasetCategory] = {}
        colors = ["#e36a22", "#237a57", "#3267c8", "#a650b5", "#b84336", "#9b6415"]
        for index, category in enumerate(parsed.payload["categories"]):
            row = DatasetCategory(id=str(uuid4()), dataset_id=dataset_id, name=category["name"], color=colors[index % len(colors)])
            category_rows[category["id"]] = row
            session.add(row)

        assets_by_image_id: dict[int, Asset] = {}
        for image in parsed.payload["images"]:
            source_file = parsed.source_files[image["id"]]
            content_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
            asset_id = str(uuid4())
            relative = Path("uploads") / "assets" / dataset_id / content_hash[:2] / f"{asset_id}{source_file.suffix.lower()}"
            destination = project_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)
            copied.append(destination)
            mime_type = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
                ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff", ".avif": "image/avif",
            }.get(source_file.suffix.lower(), "application/octet-stream")
            asset = Asset(
                id=asset_id, dataset_id=dataset_id, filename=image["file_name"], storage_path=relative.as_posix(),
                sha256=content_hash, mime_type=mime_type, width=image["width"], height=image["height"],
                size_bytes=source_file.stat().st_size, tags_json="[]",
            )
            session.add(asset)
            assets_by_image_id[image["id"]] = asset
            asset_ids.append(asset_id)

        annotations_by_image: dict[int, list[dict]] = {}
        for annotation in parsed.payload["annotations"]:
            annotations_by_image.setdefault(annotation["image_id"], []).append(annotation)
        for image in parsed.payload["images"]:
            asset = assets_by_image_id[image["id"]]
            shapes = []
            for annotation in annotations_by_image.get(image["id"], []):
                x, y, width, height = annotation["bbox"]
                shapes.append({
                    "id": str(uuid4()), "labelId": category_rows[annotation["category_id"]].id, "kind": "rectangle",
                    "points": [[x / image["width"], y / image["height"]], [(x + width) / image["width"], (y + height) / image["height"]]],
                })
            document = {
                "assetId": asset.id, "task": "detect", "imageWidth": image["width"], "imageHeight": image["height"],
                "status": "REVIEWED", "shapes": shapes,
            }
            session.add(Annotation(id=str(uuid4()), asset_id=asset.id, task="detect", status="REVIEWED", document_json=json.dumps(document, ensure_ascii=False)))

        session.commit()
        split_counts = {key: len(value) for key, value in _split_assets(list(assets_by_image_id.values()), train_ratio, val_ratio, 0, seed).items()}
        version = create_snapshot(session, project_root, dataset, DatasetVersionCreate(
            name=f"{name}-v1", train_ratio=train_ratio, val_ratio=val_ratio, test_ratio=0.0, seed=seed,
        ))
        report = {
            "sourceFormat": "VOC", "totalImages": len(parsed.payload["images"]), "importedImages": len(assets_by_image_id),
            "annotationCount": len(parsed.payload["annotations"]), "categories": [item["name"] for item in parsed.payload["categories"]],
            "repairedXml": len(parsed.repaired_files), "repairedFiles": parsed.repaired_files,
            "split": split_counts, "seed": seed,
        }
        return dataset, version, report
    except VocImportError:
        _cleanup_import_records(session, dataset_id, asset_ids, project_root, copied, snapshot_before)
        raise
    except Exception as error:
        _cleanup_import_records(session, dataset_id, asset_ids, project_root, copied, snapshot_before)
        raise VocImportError("IMPORT_FAILED", "数据集导入失败") from error
