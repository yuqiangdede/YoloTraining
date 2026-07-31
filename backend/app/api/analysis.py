import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.api.models import _resolve_video_model
from app.models import AnalysisJob, Dataset
from app.schemas.analysis import AnalysisCreate
from app.services.state_machine import JobStatus


router = APIRouter(prefix="/datasets/{dataset_id}/analysis-jobs", tags=["analysis"])


def analysis_json(item: AnalysisJob) -> dict:
    return {
        "id": item.id, "datasetId": item.dataset_id, "modelId": item.model_id, "task": item.task,
        "status": item.status, "progress": item.progress, "params": json.loads(item.params_json),
        "result": json.loads(item.result_json or "{}"), "errorMessage": item.error_message,
        "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_analysis_job(dataset_id: str, payload: AnalysisCreate, request: Request, session: Session = Depends(get_session)) -> dict:
    dataset = session.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集不存在"})
    model_path, task, _ = _resolve_video_model(request, payload.model_id, "pt", session)
    if task != dataset.task:
        raise HTTPException(422, detail={"code": "TASK_MISMATCH", "message": "模型任务类型与数据集不一致"})
    item = AnalysisJob(
        id=str(uuid4()), dataset_id=dataset_id, model_id=payload.model_id,
        model_path=request.app.state.paths.relative(model_path), task=task, status=JobStatus.QUEUED,
        params_json=json.dumps({"confidence": payload.confidence, "iouThreshold": payload.iou_threshold}),
    )
    session.add(item)
    session.commit()
    return {"data": analysis_json(item)}


@router.get("")
def list_analysis_jobs(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    if not session.get(Dataset, dataset_id):
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集不存在"})
    items = session.scalars(select(AnalysisJob).where(AnalysisJob.dataset_id == dataset_id).order_by(AnalysisJob.created_at.desc()))
    return {"data": [analysis_json(item) for item in items]}


@router.post("/{job_id}/cancel")
def cancel_analysis_job(dataset_id: str, job_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(AnalysisJob, job_id)
    if not item or item.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "ANALYSIS_JOB_NOT_FOUND", "message": "分析任务不存在"})
    if item.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
        item.status = JobStatus.CANCELLED
        session.commit()
    return {"data": analysis_json(item)}
