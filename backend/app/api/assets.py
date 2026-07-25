import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Annotation, Asset, Dataset, DatasetCategory
from app.schemas.annotations import AnnotationDocument
from app.schemas.common import ApiModel


router = APIRouter(tags=["assets"])


ANNOTATION_STATUSES = {"UNLABELED", "DRAFT", "COMPLETED", "REVIEWED"}


class AssetUpdate(ApiModel):
    is_deleted: bool


def asset_json(asset: Asset, annotation_status: str | None = None) -> dict:
    return {
        "id": asset.id, "filename": asset.filename, "storagePath": asset.storage_path,
        "sha256": asset.sha256, "mimeType": asset.mime_type, "width": asset.width,
        "height": asset.height, "sizeBytes": asset.size_bytes, "tags": json.loads(asset.tags_json),
        "isDeleted": asset.is_deleted, "annotationStatus": annotation_status or "UNLABELED",
        "createdAt": asset.created_at.isoformat(),
    }


@router.post("/datasets/{dataset_id}/assets", status_code=status.HTTP_201_CREATED)
async def upload_assets(
    dataset_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
) -> dict:
    created: list[dict] = []
    duplicate_names: list[str] = []
    root: Path = request.app.state.root
    if not session.get(Dataset, dataset_id):
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集不存在"})
    for upload in files:
        content = await upload.read()
        digest = hashlib.sha256(content).hexdigest()
        if session.scalar(select(Asset).where(Asset.dataset_id == dataset_id, Asset.sha256 == digest)):
            duplicate_names.append(upload.filename or "unknown")
            continue
        try:
            from io import BytesIO
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
        except (UnidentifiedImageError, OSError):
            raise HTTPException(422, detail={"code": "INVALID_IMAGE", "message": "文件不是有效图片"})
        asset_id = str(uuid4())
        suffix = Path(upload.filename or "image").suffix.lower() or ".bin"
        filename = Path(upload.filename or f"{asset_id}{suffix}").name
        relative = Path("uploads") / "assets" / dataset_id / digest[:2] / f"{asset_id}{suffix}"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        asset = Asset(
            id=asset_id, dataset_id=dataset_id, filename=filename, storage_path=relative.as_posix(), sha256=digest,
            mime_type=upload.content_type or "application/octet-stream", width=width,
            height=height, size_bytes=len(content), tags_json="[]",
        )
        session.add(asset)
        session.commit()
        created.append(asset_json(asset))
    if duplicate_names and not created:
        raise HTTPException(409, detail={"code": "DUPLICATE_ASSET", "message": "图片内容已存在", "details": duplicate_names})
    return {"data": created, "duplicates": duplicate_names}


@router.get("/datasets/{dataset_id}/assets")
def list_assets(
    dataset_id: str,
    page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    search: str | None = None, include_deleted: bool = Query(False, alias="includeDeleted"),
    annotation_statuses: list[str] | None = Query(None, alias="annotationStatus"),
    session: Session = Depends(get_session),
) -> dict:
    if not session.get(Dataset, dataset_id):
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集不存在"})
    filters = [Asset.dataset_id == dataset_id]
    if not include_deleted:
        filters.append(Asset.is_deleted.is_(False))
    if search:
        filters.append(or_(Asset.filename.contains(search), Asset.tags_json.contains(search)))
    normalized_statuses = {value.upper() for value in annotation_statuses or []}
    unknown_statuses = normalized_statuses - ANNOTATION_STATUSES
    if unknown_statuses:
        raise HTTPException(422, detail={"code": "INVALID_ANNOTATION_STATUS", "message": "标注状态无效", "details": sorted(unknown_statuses)})
    status_filters = []
    persisted_statuses = normalized_statuses - {"UNLABELED"}
    if persisted_statuses:
        status_filters.append(Annotation.status.in_(persisted_statuses))
    if "UNLABELED" in normalized_statuses:
        status_filters.append(Annotation.id.is_(None))
    if status_filters:
        filters.append(or_(*status_filters))
    base = select(Asset, Annotation.status).outerjoin(Annotation, Annotation.asset_id == Asset.id).where(*filters)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    query = base.order_by(Asset.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = [asset_json(asset, annotation_status) for asset, annotation_status in session.execute(query)]
    return {"data": items, "pagination": {"page": page, "pageSize": page_size, "totalItems": total, "totalPages": (total + page_size - 1) // page_size}}


@router.put("/datasets/{dataset_id}/assets/{asset_id}/annotation")
def save_annotation(dataset_id: str, asset_id: str, document: AnnotationDocument, session: Session = Depends(get_session)) -> dict:
    asset = session.get(Asset, asset_id)
    if asset_id != document.asset_id or not asset or asset.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "素材不存在"})
    known_categories = set(session.scalars(select(DatasetCategory.id).where(DatasetCategory.dataset_id == dataset_id)))
    dataset = session.get(Dataset, dataset_id)
    if dataset and document.task.value != dataset.task:
        raise HTTPException(422, detail={"code": "TASK_MISMATCH", "message": "Annotation task does not match dataset task"})
    unknown = sorted({shape.label_id for shape in document.shapes} - known_categories)
    if unknown:
        raise HTTPException(422, detail={"code": "UNKNOWN_CATEGORY", "message": "标注包含不存在的类别", "details": {"categoryIds": unknown}})
    current = session.scalar(select(Annotation).where(Annotation.asset_id == asset_id))
    # Older clients send REVIEWED for their single save action. Treat that as
    # completion while keeping REVIEWED available for future explicit review.
    persisted_status = "COMPLETED" if document.status == "REVIEWED" else document.status
    payload = document.model_dump_json(by_alias=True)
    if current:
        current.document_json = payload
        current.status = persisted_status
        current.task = document.task
        current.version += 1
    else:
        current = Annotation(id=str(uuid4()), asset_id=asset_id, task=document.task, status=persisted_status, document_json=payload)
        session.add(current)
    session.commit()
    return {"id": current.id, "assetId": asset_id, "version": current.version, "status": current.status}


@router.get("/datasets/{dataset_id}/assets/{asset_id}/annotation")
def get_annotation(dataset_id: str, asset_id: str, session: Session = Depends(get_session)) -> dict:
    asset = session.get(Asset, asset_id)
    if not asset or asset.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "素材不存在"})
    annotation = session.scalar(select(Annotation).where(Annotation.asset_id == asset_id))
    if not annotation:
        return {"data": None}
    return {"data": json.loads(annotation.document_json)}


@router.delete("/datasets/{dataset_id}/assets/{asset_id}")
def recycle_asset(dataset_id: str, asset_id: str, session: Session = Depends(get_session)) -> dict:
    asset = session.get(Asset, asset_id)
    if not asset or asset.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "素材不存在"})
    asset.is_deleted = True
    session.commit()
    return {"id": asset_id, "isDeleted": True}


@router.patch("/datasets/{dataset_id}/assets/{asset_id}")
def update_asset(dataset_id: str, asset_id: str, payload: AssetUpdate, session: Session = Depends(get_session)) -> dict:
    asset = session.get(Asset, asset_id)
    if not asset or asset.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "素材不存在"})
    asset.is_deleted = payload.is_deleted
    annotation_status = session.scalar(select(Annotation.status).where(Annotation.asset_id == asset_id))
    session.commit()
    return asset_json(asset, annotation_status)
