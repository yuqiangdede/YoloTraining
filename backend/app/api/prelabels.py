import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Asset, PrelabelJob
from app.schemas.annotations import TaskType
from app.schemas.common import ApiModel
from app.services.state_machine import JobStatus


router = APIRouter(prefix="/prelabel-jobs", tags=["prelabels"])


class PrelabelCreate(ApiModel):
    model_path: str
    task: TaskType
    asset_ids: list[str] = Field(min_length=1)
    confidence: float = Field(default=0.25, ge=0, le=1)


def prelabel_json(item: PrelabelJob) -> dict:
    return {
        "id": item.id, "modelPath": item.model_path, "task": item.task, "status": item.status,
        "params": json.loads(item.params_json), "result": json.loads(item.result_json),
        "errorMessage": item.error_message, "createdAt": item.created_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_prelabel(request: Request, payload: PrelabelCreate, session: Session = Depends(get_session)) -> dict:
    model = request.app.state.paths.resolve(payload.model_path)
    if not payload.model_path.replace("\\", "/").startswith("models/") or not model.is_file():
        raise HTTPException(422, detail={"code": "MODEL_NOT_FOUND", "message": "预标注模型必须位于项目 models 目录"})
    found = set(session.scalars(select(Asset.id).where(Asset.id.in_(payload.asset_ids), Asset.is_deleted.is_(False))))
    if found != set(payload.asset_ids):
        raise HTTPException(422, detail={"code": "ASSET_NOT_FOUND", "message": "部分素材不存在"})
    item = PrelabelJob(
        id=str(uuid4()), model_path=payload.model_path, task=payload.task,
        status=JobStatus.QUEUED, params_json=payload.model_dump_json(by_alias=True), result_json="{}",
    )
    session.add(item)
    session.commit()
    return prelabel_json(item)


@router.get("")
def list_prelabels(session: Session = Depends(get_session)) -> dict:
    return {"data": [prelabel_json(item) for item in session.scalars(select(PrelabelJob).order_by(PrelabelJob.created_at.desc()))]}
