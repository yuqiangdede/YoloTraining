import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Annotation, Asset
from app.schemas.annotations import AnnotationDocument


router = APIRouter(prefix="/assets", tags=["assets"])


def asset_json(asset: Asset) -> dict:
    return {
        "id": asset.id, "filename": asset.filename, "storagePath": asset.storage_path,
        "sha256": asset.sha256, "mimeType": asset.mime_type, "width": asset.width,
        "height": asset.height, "sizeBytes": asset.size_bytes, "tags": json.loads(asset.tags_json),
        "isDeleted": asset.is_deleted, "createdAt": asset.created_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_assets(
    request: Request,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
) -> dict:
    created: list[dict] = []
    duplicate_names: list[str] = []
    root: Path = request.app.state.root
    for upload in files:
        content = await upload.read()
        digest = hashlib.sha256(content).hexdigest()
        if session.scalar(select(Asset).where(Asset.sha256 == digest)):
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
        relative = Path("uploads") / "assets" / digest[:2] / f"{asset_id}{suffix}"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        asset = Asset(
            id=asset_id, filename=filename, storage_path=relative.as_posix(), sha256=digest,
            mime_type=upload.content_type or "application/octet-stream", width=width,
            height=height, size_bytes=len(content), tags_json="[]",
        )
        session.add(asset)
        session.commit()
        created.append(asset_json(asset))
    if duplicate_names and not created:
        raise HTTPException(409, detail={"code": "DUPLICATE_ASSET", "message": "图片内容已存在", "details": duplicate_names})
    return {"data": created, "duplicates": duplicate_names}


@router.get("")
def list_assets(
    page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    search: str | None = None, include_deleted: bool = Query(False, alias="includeDeleted"),
    session: Session = Depends(get_session),
) -> dict:
    filters = []
    if not include_deleted:
        filters.append(Asset.is_deleted.is_(False))
    if search:
        filters.append(or_(Asset.filename.contains(search), Asset.tags_json.contains(search)))
    total = session.scalar(select(func.count()).select_from(Asset).where(*filters)) or 0
    query = select(Asset).where(*filters).order_by(Asset.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = [asset_json(asset) for asset in session.scalars(query)]
    return {"data": items, "pagination": {"page": page, "pageSize": page_size, "totalItems": total, "totalPages": (total + page_size - 1) // page_size}}


@router.put("/{asset_id}/annotation")
def save_annotation(asset_id: str, document: AnnotationDocument, session: Session = Depends(get_session)) -> dict:
    if asset_id != document.asset_id or not session.get(Asset, asset_id):
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "素材不存在"})
    current = session.scalar(select(Annotation).where(Annotation.asset_id == asset_id))
    payload = document.model_dump_json(by_alias=True)
    if current:
        current.document_json = payload
        current.status = document.status
        current.task = document.task
        current.version += 1
    else:
        current = Annotation(id=str(uuid4()), asset_id=asset_id, task=document.task, status=document.status, document_json=payload)
        session.add(current)
    session.commit()
    return {"id": current.id, "assetId": asset_id, "version": current.version, "status": current.status}


@router.get("/{asset_id}/annotation")
def get_annotation(asset_id: str, session: Session = Depends(get_session)) -> dict:
    annotation = session.scalar(select(Annotation).where(Annotation.asset_id == asset_id))
    if not annotation:
        return {"data": None}
    return {"data": json.loads(annotation.document_json)}


@router.delete("/{asset_id}")
def recycle_asset(asset_id: str, session: Session = Depends(get_session)) -> dict:
    asset = session.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "素材不存在"})
    asset.is_deleted = True
    session.commit()
    return {"id": asset_id, "isDeleted": True}
