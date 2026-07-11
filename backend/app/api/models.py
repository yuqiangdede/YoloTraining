import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import ExportJob, ModelArtifact
from app.schemas.common import ApiModel
from app.services.state_machine import JobStatus


router = APIRouter(prefix="/models", tags=["models"])


class ExportCreate(ApiModel):
    format: str = Field(pattern="^onnx$")
    imgsz: int = Field(default=640, ge=32, le=8192)
    dynamic: bool = False
    simplify: bool = True
    opset: int | None = Field(default=None, ge=9, le=21)


def export_json(item: ExportJob) -> dict:
    return {
        "id": item.id, "artifactId": item.artifact_id, "format": item.format,
        "status": item.status, "params": json.loads(item.params_json),
        "outputPath": item.output_path, "errorMessage": item.error_message,
        "createdAt": item.created_at.isoformat(),
    }


@router.get("")
def list_models(request: Request, session: Session = Depends(get_session)) -> dict:
    artifacts = [{
        "id": item.id, "name": item.name, "task": item.task, "path": item.path,
        "kind": item.kind, "sha256": item.sha256, "metrics": json.loads(item.metrics_json),
    } for item in session.scalars(select(ModelArtifact).order_by(ModelArtifact.created_at.desc()))]
    pretrained = []
    for path in sorted((request.app.state.root / "models" / "pretrained").glob("*.pt")):
        pretrained.append({"name": path.name, "path": path.relative_to(request.app.state.root).as_posix(), "kind": "PRETRAINED", "sizeBytes": path.stat().st_size})
    return {"data": artifacts, "pretrained": pretrained}


@router.get("/{artifact_id}/download")
def download_model(request: Request, artifact_id: str, session: Session = Depends(get_session)) -> FileResponse:
    artifact = session.get(ModelArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "MODEL_NOT_FOUND", "message": "模型产物不存在"})
    path = request.app.state.paths.resolve(artifact.path)
    if not path.is_file():
        raise HTTPException(404, detail={"code": "MODEL_FILE_MISSING", "message": "模型文件缺失"})
    return FileResponse(path, filename=artifact.name, media_type="application/octet-stream")


@router.post("/{artifact_id}/exports", status_code=status.HTTP_201_CREATED)
def create_export(request: Request, artifact_id: str, payload: ExportCreate, session: Session = Depends(get_session)) -> dict:
    artifact = session.get(ModelArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "MODEL_NOT_FOUND", "message": "模型产物不存在"})
    if not request.app.state.paths.resolve(artifact.path).is_file():
        raise HTTPException(422, detail={"code": "MODEL_FILE_MISSING", "message": "模型文件缺失"})
    item = ExportJob(
        id=str(uuid4()), artifact_id=artifact.id, format=payload.format,
        status=JobStatus.QUEUED, params_json=payload.model_dump_json(by_alias=True),
    )
    session.add(item)
    session.commit()
    return export_json(item)


@router.get("/exports")
def list_exports(session: Session = Depends(get_session)) -> dict:
    return {"data": [export_json(item) for item in session.scalars(select(ExportJob).order_by(ExportJob.created_at.desc()))]}
