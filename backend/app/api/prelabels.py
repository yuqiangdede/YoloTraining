import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Asset, Dataset, PrelabelJob
from app.schemas.annotations import TaskType
from app.schemas.common import ApiModel
from app.services.state_machine import JobStatus


router = APIRouter(prefix="/prelabel-jobs", tags=["prelabels"])


DEFAULT_PRELABEL_MODEL = {
    TaskType.DETECT: "models/pretrained/yolo26n.pt",
    TaskType.SEGMENT: "models/pretrained/yolo26n-seg.pt",
    TaskType.SEMANTIC: "models/pretrained/yolo26n-sem.pt",
    TaskType.POSE: "models/pretrained/yolo26n-pose.pt",
    TaskType.OBB: "models/pretrained/yolo26n-obb.pt",
}


class PrelabelCreate(ApiModel):
    model_path: str
    task: TaskType
    asset_ids: list[str] = Field(min_length=1)
    confidence: float = Field(default=0.25, ge=0, le=1)
    mode: Literal["yolo", "yolo_sam", "sam"] = "yolo"


class DatasetPrelabelCreate(ApiModel):
    model_path: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    mode: Literal["yolo", "yolo_sam", "sam"] | None = None


def prelabel_json(item: PrelabelJob) -> dict:
    return {
        "id": item.id, "modelPath": item.model_path, "task": item.task, "status": item.status,
        "datasetId": item.dataset_id,
        "params": json.loads(item.params_json), "result": json.loads(item.result_json),
        "errorMessage": item.error_message, "createdAt": item.created_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_prelabel(request: Request, payload: PrelabelCreate, session: Session = Depends(get_session)) -> dict:
    model = request.app.state.paths.resolve(payload.model_path)
    if payload.mode in {"yolo", "yolo_sam"} and (not payload.model_path.replace("\\", "/").startswith("models/") or not model.is_file()):
        raise HTTPException(422, detail={"code": "MODEL_NOT_FOUND", "message": "预标注模型必须位于项目 models 目录"})
    found = set(session.scalars(select(Asset.id).where(Asset.id.in_(payload.asset_ids), Asset.is_deleted.is_(False))))
    if found != set(payload.asset_ids):
        raise HTTPException(422, detail={"code": "ASSET_NOT_FOUND", "message": "部分素材不存在"})
    if payload.mode in {"yolo_sam", "sam"}:
        if payload.task not in {TaskType.DETECT, TaskType.SEGMENT}:
            raise HTTPException(422, detail={"code": "SAM_REQUIRES_DETECT_OR_SEGMENT_TASK", "message": "SAM only supports detection or instance-segmentation datasets"})
        if not request.app.state.paths.resolve("models/pretrained/sam3.pt").is_file():
            raise HTTPException(422, detail={"code": "SAM_MODEL_NOT_FOUND", "message": "SAM3 model file is missing"})
    item = PrelabelJob(
        id=str(uuid4()), model_path=payload.model_path, task=payload.task,
        status=JobStatus.QUEUED, params_json=payload.model_dump_json(by_alias=True), result_json="{}",
    )
    session.add(item)
    session.commit()
    return prelabel_json(item)


@router.post("/datasets/{dataset_id}", status_code=status.HTTP_201_CREATED)
def create_dataset_prelabel(dataset_id: str, request: Request, payload: DatasetPrelabelCreate, session: Session = Depends(get_session)) -> dict:
    dataset = session.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集不存在"})
    mode = payload.mode if payload.mode is not None else dataset.prelabel_mode
    confidence = payload.confidence if payload.confidence is not None else dataset.prelabel_confidence
    # Dataset-level YOLO prelabeling deliberately has no model-size setting.
    # Keep an explicitly supplied path for API compatibility, but default every
    # YOLO task to its n-sized checkpoint and ignore legacy saved m/l/x paths.
    model_path = payload.model_path if payload.model_path is not None else (
        DEFAULT_PRELABEL_MODEL[dataset.task] if mode in {"yolo", "yolo_sam"} else None
    )
    if mode in {"yolo", "yolo_sam"} and not model_path:
        raise HTTPException(422, detail={"code": "MODEL_REQUIRED", "message": "请先选择预标注模型"})
    model = request.app.state.paths.resolve(model_path) if model_path else None
    if mode in {"yolo", "yolo_sam"} and (not model_path.replace("\\", "/").startswith("models/") or not model or not model.is_file()):
        raise HTTPException(422, detail={"code": "MODEL_NOT_FOUND", "message": "预标注模型必须位于项目 models 目录"})
    if mode in {"yolo_sam", "sam"}:
        if dataset.task not in {TaskType.DETECT, TaskType.SEGMENT}:
            raise HTTPException(422, detail={"code": "SAM_REQUIRES_DETECT_OR_SEGMENT_TASK", "message": "SAM 预标注仅支持目标检测或实例分割数据集"})
        if not request.app.state.paths.resolve("models/pretrained/sam3.pt").is_file():
            raise HTTPException(422, detail={"code": "SAM_MODEL_NOT_FOUND", "message": "SAM3 模型文件不存在"})
    asset_ids = list(session.scalars(select(Asset.id).where(Asset.dataset_id == dataset_id, Asset.is_deleted.is_(False))))
    if not asset_ids:
        raise HTTPException(422, detail={"code": "DATASET_EMPTY", "message": "数据集没有可预标注的素材"})
    job_model_path = model_path or "models/pretrained/sam3.pt"
    params = {"modelPath": job_model_path, "task": dataset.task, "assetIds": asset_ids, "confidence": confidence, "mode": mode, "datasetId": dataset_id}
    item = PrelabelJob(id=str(uuid4()), dataset_id=dataset_id, model_path=job_model_path, task=dataset.task,
                       status=JobStatus.QUEUED, params_json=json.dumps(params, ensure_ascii=False), result_json="{}")
    dataset.prelabel_model_path, dataset.prelabel_mode, dataset.prelabel_confidence = model_path, mode, confidence
    session.add(item); session.commit()
    return prelabel_json(item)


@router.get("")
def list_prelabels(dataset_id: str | None = None, session: Session = Depends(get_session)) -> dict:
    query = select(PrelabelJob).order_by(PrelabelJob.created_at.desc())
    if dataset_id:
        query = query.where(PrelabelJob.dataset_id == dataset_id)
    return {"data": [prelabel_json(item) for item in session.scalars(query)]}
