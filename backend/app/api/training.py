import json
import shutil
from importlib.util import find_spec
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import DatasetVersion, ExportJob, ModelArtifact, PrelabelJob, TrainingJob, VideoInferenceJob
from app.schemas.training import RFDETR_MODELS, RFDETR_TRAIN_FIELDS, TrainRequest
from app.services.dataset_builder import DatasetSplitError, validate_snapshot_split
from app.services.rfdetr_training import validation_rows
from app.services.state_machine import JobStatus, transition
from app.services.training_metrics import summarize_results, summarize_results_file


router = APIRouter(prefix="/training-jobs", tags=["training"])


def job_json(job: TrainingJob, queue_info: dict | None = None) -> dict:
    params = json.loads(job.params_json)
    payload = {
        "id": job.id, "name": job.name, "datasetVersionId": job.dataset_version_id,
        "task": job.task, "modelPath": job.model_path, "runPath": job.run_path,
        "status": job.status, "params": params, "progress": job.progress,
        "engine": params.get("engine", "yolo"),
        "modelVariant": RFDETR_MODELS.get(job.model_path, (None, None))[0],
        "currentEpoch": job.current_epoch, "errorMessage": job.error_message,
        "createdAt": job.created_at.isoformat(), "updatedAt": job.updated_at.isoformat(),
    }
    if queue_info:
        payload.update(queue_info)
    return payload


def _queue_info(session: Session) -> dict[str, dict]:
    queued: list[tuple[str, object]] = []
    for model in (TrainingJob, ExportJob, PrelabelJob, VideoInferenceJob):
        queued.extend((model.__name__, item) for item in session.scalars(
            select(model).where(model.status == JobStatus.QUEUED)
        ))
    queued.sort(key=lambda pair: pair[1].created_at)
    running = any(
        session.scalar(select(model).where(model.status.in_([JobStatus.RUNNING, JobStatus.PAUSING])))
        for model in (TrainingJob, ExportJob, PrelabelJob, VideoInferenceJob)
    )
    offset = 1 if running else 0
    now = datetime.now(timezone.utc)
    result: dict[str, dict] = {}
    for index, (kind, item) in enumerate(queued):
        if kind != "TrainingJob":
            continue
        created = item.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        result[item.id] = {
            "queuePosition": index + 1 + offset,
            "queueSize": len(queued) + offset,
            "waitSeconds": max(0, int((now - created).total_seconds())),
        }
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def create_training_job(request: Request, payload: TrainRequest, session: Session = Depends(get_session)) -> dict:
    dataset = session.get(DatasetVersion, payload.dataset_version_id)
    if not dataset:
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集版本不存在"})
    if dataset.task != payload.task:
        raise HTTPException(422, detail={"code": "TASK_MISMATCH", "message": "模型任务与数据集不一致"})
    manifest = json.loads(dataset.manifest_json)
    try:
        validate_snapshot_split(request.app.state.root / dataset.snapshot_path,
                                require_validation=payload.engine == "rfdetr" or manifest.get("valRatio", 1) > 0)
    except DatasetSplitError as error:
        raise HTTPException(422, detail={"code": "INVALID_DATASET_SPLIT", "message": str(error)}) from error
    model = request.app.state.paths.resolve(payload.model_path)
    if not model.is_file():
        raise HTTPException(422, detail={"code": "MODEL_NOT_FOUND", "message": "项目内模型文件不存在"})
    if payload.engine == "rfdetr" and any(find_spec(package) is None for package in ("rfdetr", "pytorch_lightning")):
        raise HTTPException(503, detail={"code": "RFDETR_NOT_INSTALLED", "message": "请先安装 RF-DETR 训练依赖"})
    job_id = str(uuid4())
    run_path = f"runs/{job_id}"
    job = TrainingJob(
        id=job_id, name=payload.name, dataset_version_id=dataset.id, task=payload.task,
        model_path=payload.model_path, run_path=run_path, status=JobStatus.QUEUED,
        params_json=payload.model_dump_json(by_alias=True, include=RFDETR_TRAIN_FIELDS if payload.engine == "rfdetr" else None),
    )
    session.add(job)
    session.commit()
    return job_json(job)


@router.get("")
def list_training_jobs(request: Request, session: Session = Depends(get_session)) -> dict:
    jobs = session.scalars(select(TrainingJob).order_by(TrainingJob.created_at.desc()))
    queue = _queue_info(session)
    return {"data": [job_json(job, queue.get(job.id)) for job in jobs], "worker": request.app.state.worker.health()}


@router.get("/{job_id}")
def get_training_job(job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "训练任务不存在"})
    return job_json(job)


@router.delete("/{job_id}")
def delete_training_job(job_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    job = session.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "训练任务不存在"})
    if job.status in {JobStatus.RUNNING, JobStatus.PAUSING}:
        raise HTTPException(409, detail={"code": "JOB_RUNNING", "message": "运行中的训练任务请先取消后再删除"})
    if (job.status == JobStatus.CANCELLED and json.loads(job.params_json).get("engine") == "rfdetr"
            and request.app.state.worker.health()["currentJobId"] == job_id):
        raise HTTPException(409, detail={"code": "JOB_STOPPING", "message": "请等待 RF-DETR 训练进程退出后再删除"})

    artifacts = list(session.scalars(select(ModelArtifact).where(ModelArtifact.training_job_id == job_id)))
    artifact_ids = [item.id for item in artifacts]
    exports = list(session.scalars(select(ExportJob).where(ExportJob.artifact_id.in_(artifact_ids)))) if artifact_ids else []
    for artifact in artifacts:
        request.app.state.paths.resolve(artifact.path).unlink(missing_ok=True)
    for export in exports:
        if export.output_path:
            request.app.state.paths.resolve(export.output_path).unlink(missing_ok=True)
        shutil.rmtree(request.app.state.root / "runs" / "exports" / export.id, ignore_errors=True)
    shutil.rmtree(request.app.state.root / job.run_path, ignore_errors=True)
    if artifact_ids:
        session.query(ExportJob).filter(ExportJob.artifact_id.in_(artifact_ids)).delete(synchronize_session=False)
    session.query(ModelArtifact).filter(ModelArtifact.training_job_id == job_id).delete(synchronize_session=False)
    session.delete(job)
    session.commit()
    return {"id": job_id, "deleted": True}


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
    if json.loads(job.params_json).get("engine") == "rfdetr":
        raise HTTPException(422, detail={"code": "RFDETR_ACTION_UNSUPPORTED", "message": "RF-DETR 暂不支持暂停或续训"})
    job.status = transition(JobStatus(job.status), target)
    session.commit()
    return job


@router.post("/{job_id}/cancel")
def cancel_job(request: Request, job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "训练任务不存在"})
    target = JobStatus.CANCELLED
    if json.loads(job.params_json).get("engine") == "rfdetr":
        changed = session.execute(update(TrainingJob).where(
            TrainingJob.id == job_id, TrainingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        ).values(status=target)).rowcount
        if not changed:
            raise HTTPException(409, detail={"code": "JOB_NOT_CANCELLABLE", "message": "任务已结束，无法取消"})
        session.commit()
        session.refresh(job)
        return job_json(job)
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
def list_artifacts(request: Request, job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(TrainingJob, job_id)
    items = session.scalars(select(ModelArtifact).where(ModelArtifact.training_job_id == job_id))
    payload = {"data": [{
        "id": item.id, "trainingJobId": item.training_job_id, "task": item.task,
        "name": item.name, "path": item.path, "kind": item.kind, "sha256": item.sha256,
        "engine": "rfdetr" if item.kind == "RFDETR" else "yolo",
        "modelVariant": RFDETR_MODELS.get(job.model_path, (None, None))[0] if job and item.kind == "RFDETR" else None,
        "metrics": json.loads(item.metrics_json),
        "trainingQuality": json.loads(item.training_quality_json) if item.training_quality_json and item.training_quality_json != "{}" else summarize_results_file(next(iter((request.app.state.root / "runs" / job_id).rglob("results.csv")), None), item.task),
        "createdAt": item.created_at.isoformat(),
    } for item in items]}
    if job and json.loads(job.params_json).get("engine") == "rfdetr" and not payload["data"]:
        try:
            rows = validation_rows(request.app.state.root / job.run_path)
        except (OSError, ValueError):
            # Lightning 可能正在刷新 CSV，下一次轮询会重新读取。
            rows = []
        if rows:
            payload["trainingQuality"] = summarize_results(rows, job.task)
    return payload
