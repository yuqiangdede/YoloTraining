import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import DatasetVersion, ModelArtifact, TrainingJob
from app.schemas.training import TrainRequest
from app.services.state_machine import JobStatus, transition


router = APIRouter(prefix="/training-jobs", tags=["training"])


def job_json(job: TrainingJob) -> dict:
    return {
        "id": job.id, "name": job.name, "datasetVersionId": job.dataset_version_id,
        "task": job.task, "modelPath": job.model_path, "runPath": job.run_path,
        "status": job.status, "params": json.loads(job.params_json), "progress": job.progress,
        "currentEpoch": job.current_epoch, "errorMessage": job.error_message,
        "createdAt": job.created_at.isoformat(), "updatedAt": job.updated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_training_job(request: Request, payload: TrainRequest, session: Session = Depends(get_session)) -> dict:
    dataset = session.get(DatasetVersion, payload.dataset_version_id)
    if not dataset:
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集版本不存在"})
    if dataset.task != payload.task:
        raise HTTPException(422, detail={"code": "TASK_MISMATCH", "message": "模型任务与数据集不一致"})
    model = request.app.state.paths.resolve(payload.model_path)
    if not model.is_file():
        raise HTTPException(422, detail={"code": "MODEL_NOT_FOUND", "message": "项目内模型文件不存在"})
    job_id = str(uuid4())
    run_path = f"runs/{job_id}"
    job = TrainingJob(
        id=job_id, name=payload.name, dataset_version_id=dataset.id, task=payload.task,
        model_path=payload.model_path, run_path=run_path, status=JobStatus.QUEUED,
        params_json=payload.model_dump_json(by_alias=True),
    )
    session.add(job)
    session.commit()
    return job_json(job)


@router.get("")
def list_training_jobs(session: Session = Depends(get_session)) -> dict:
    jobs = session.scalars(select(TrainingJob).order_by(TrainingJob.created_at.desc()))
    return {"data": [job_json(job) for job in jobs]}


@router.get("/{job_id}")
def get_training_job(job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "训练任务不存在"})
    return job_json(job)


@router.get("/{job_id}/log")
def get_training_log(request: Request, job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "训练任务不存在"})
    path = request.app.state.paths.resolve(f"{job.run_path}/train.log")
    if not path.exists():
        return {"content": "", "sizeBytes": 0}
    content = path.read_text(encoding="utf-8", errors="replace")
    return {"content": content[-100_000:], "sizeBytes": path.stat().st_size}


def _action(job_id: str, target: JobStatus, session: Session) -> TrainingJob:
    job = session.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "训练任务不存在"})
    job.status = transition(JobStatus(job.status), target)
    session.commit()
    return job


@router.post("/{job_id}/cancel")
def cancel_job(request: Request, job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "训练任务不存在"})
    target = JobStatus.CANCELLED
    job.status = transition(JobStatus(job.status), target)
    control = request.app.state.root / job.run_path / "control.json"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(json.dumps({"action": "cancel"}), encoding="utf-8")
    session.commit()
    return job_json(job)


@router.post("/{job_id}/pause")
def pause_job(request: Request, job_id: str, session: Session = Depends(get_session)) -> dict:
    job = _action(job_id, JobStatus.PAUSING, session)
    control = request.app.state.root / job.run_path / "control.json"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(json.dumps({"action": "pause"}), encoding="utf-8")
    return job_json(job)


@router.post("/{job_id}/resume")
def resume_job(job_id: str, session: Session = Depends(get_session)) -> dict:
    job = _action(job_id, JobStatus.QUEUED, session)
    params = json.loads(job.params_json)
    params["resume"] = True
    job.params_json = json.dumps(params, ensure_ascii=False)
    session.commit()
    return job_json(job)


@router.get("/{job_id}/artifacts")
def list_artifacts(job_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(ModelArtifact).where(ModelArtifact.training_job_id == job_id))
    return {"data": [{
        "id": item.id, "trainingJobId": item.training_job_id, "task": item.task,
        "name": item.name, "path": item.path, "kind": item.kind, "sha256": item.sha256,
        "metrics": json.loads(item.metrics_json), "createdAt": item.created_at.isoformat(),
    } for item in items]}
