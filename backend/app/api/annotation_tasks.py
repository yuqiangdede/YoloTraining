import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Annotation, AnnotationTask, Asset, Dataset
from app.schemas.annotation_tasks import AnnotationTaskCreate, AnnotationTaskUpdate


router = APIRouter(prefix="/datasets/{dataset_id}/annotation-tasks", tags=["annotation-tasks"])


def require_dataset(dataset_id: str, session: Session) -> None:
    if not session.get(Dataset, dataset_id):
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集不存在"})


def task_json(item: AnnotationTask, session: Session) -> dict:
    asset_ids = json.loads(item.asset_ids_json)
    completed = 0
    if asset_ids:
        completed = len(list(session.scalars(
            select(Annotation.id).where(Annotation.asset_id.in_(asset_ids), Annotation.status.in_(["COMPLETED", "REVIEWED"]))
        )))
    effective_status = "COMPLETED" if asset_ids and completed == len(asset_ids) else "IN_PROGRESS" if completed or item.status == "IN_PROGRESS" else item.status
    return {
        "id": item.id, "datasetId": item.dataset_id, "name": item.name, "assignee": item.assignee,
        "status": effective_status, "assetIds": asset_ids, "assetCount": len(asset_ids),
        "completedCount": completed, "progress": round(completed * 100 / len(asset_ids)) if asset_ids else 0,
        "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_annotation_task(dataset_id: str, payload: AnnotationTaskCreate, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    active_ids = set(session.scalars(select(Asset.id).where(Asset.dataset_id == dataset_id, Asset.is_deleted.is_(False))))
    requested = list(dict.fromkeys(payload.asset_ids)) if payload.asset_ids is not None else sorted(active_ids)
    unknown = sorted(set(requested) - active_ids)
    if unknown:
        raise HTTPException(422, detail={"code": "INVALID_TASK_ASSETS", "message": "任务包含不属于当前数据集的素材", "details": unknown})
    if not requested:
        raise HTTPException(422, detail={"code": "EMPTY_ANNOTATION_TASK", "message": "当前没有可分配的素材"})
    item = AnnotationTask(
        id=str(uuid4()), dataset_id=dataset_id, name=payload.name.strip(), assignee=payload.assignee.strip(),
        status="NEW", asset_ids_json=json.dumps(requested),
    )
    session.add(item)
    session.commit()
    return {"data": task_json(item, session)}


@router.get("")
def list_annotation_tasks(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    items = session.scalars(select(AnnotationTask).where(AnnotationTask.dataset_id == dataset_id).order_by(AnnotationTask.created_at.desc()))
    return {"data": [task_json(item, session) for item in items]}


@router.patch("/{task_id}")
def update_annotation_task(dataset_id: str, task_id: str, payload: AnnotationTaskUpdate, session: Session = Depends(get_session)) -> dict:
    item = session.get(AnnotationTask, task_id)
    if not item or item.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "ANNOTATION_TASK_NOT_FOUND", "message": "标注任务不存在"})
    item.assignee = payload.assignee.strip()
    item.status = payload.status
    session.commit()
    return {"data": task_json(item, session)}
