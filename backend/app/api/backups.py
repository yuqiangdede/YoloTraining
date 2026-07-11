from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field

from app.schemas.common import ApiModel
from app.services.backups import BackupService


router = APIRouter(prefix="/backups", tags=["backups"])


class BackupCreate(ApiModel):
    label: str = Field(default="manual", min_length=1, max_length=80)


def record_json(record) -> dict:
    return {"label": record.label, "path": record.path, "createdAt": record.created_at, "sizeBytes": record.size_bytes}


@router.get("")
def list_backups(request: Request) -> dict:
    return {"data": [record_json(item) for item in BackupService(request.app.state.root).list()]}


@router.post("")
def create_backup(request: Request, payload: BackupCreate) -> dict:
    return record_json(BackupService(request.app.state.root).create(payload.label))


@router.get("/{filename}/download")
def download_backup(request: Request, filename: str) -> FileResponse:
    if Path(filename).name != filename or not filename.endswith(".zip"):
        raise HTTPException(404, detail={"code": "BACKUP_NOT_FOUND", "message": "备份不存在"})
    path = request.app.state.root / "backups" / filename
    if not path.is_file():
        raise HTTPException(404, detail={"code": "BACKUP_NOT_FOUND", "message": "备份不存在"})
    return FileResponse(path, filename=filename, media_type="application/zip")
