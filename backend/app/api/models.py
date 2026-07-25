import json
import base64
import io
import shutil
import threading
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import ExportJob, ModelArtifact, TrainingJob, VideoInferenceJob
from app.schemas.common import ApiModel
from app.services.state_machine import JobStatus
from app.services.training_metrics import summarize_results_file


router = APIRouter(prefix="/models", tags=["models"])
_MODEL_CACHE: dict[str, object] = {}
_MODEL_CACHE_LOCK = threading.Lock()
MAX_PREDICT_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PREDICT_VIDEO_BYTES = 500 * 1024 * 1024
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
TESTABLE_PRETRAINED_PATTERN = re.compile(r"^yolo26[nslmx](?:-seg|-sem|-pose|-obb)?\.pt$", re.IGNORECASE)


class ExportCreate(ApiModel):
    format: str = Field(pattern="^onnx$")
    imgsz: int = Field(default=640, ge=32, le=8192)
    dynamic: bool = False
    simplify: bool = True
    opset: int | None = Field(default=None, ge=9, le=21)


def _get_cached_model(path: Path) -> object:
    key = str(path)
    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is not None:
            return model
        from ultralytics import YOLO
        model = YOLO(key)
        _MODEL_CACHE[key] = model
        return model


def _prediction_rows(result: object, task: str) -> list[dict]:
    names = getattr(result, "names", {})
    rows: list[dict] = []
    boxes = getattr(result, "boxes", None)
    obb = getattr(result, "obb", None)
    masks = getattr(result, "masks", None)
    keypoints = getattr(result, "keypoints", None)

    def label_for(index: int) -> str:
        return str(names.get(index, index) if isinstance(names, dict) else index)

    if task == "obb" and obb is not None:
        height, width = result.orig_shape
        for points, confidence, cls in zip(obb.xyxyxyxy.cpu().tolist(), obb.conf.cpu().tolist(), obb.cls.cpu().tolist()):
            points = [[point[0] / width, point[1] / height] for point in points]
            rows.append({"label": label_for(int(cls)), "confidence": round(float(confidence), 4), "kind": "polygon", "points": points})
        return rows

    if boxes is None:
        return rows
    classes = boxes.cls.cpu().tolist()
    confidences = boxes.conf.cpu().tolist()
    if task in {"segment", "semantic"} and masks is not None:
        for polygon, confidence, cls in zip(masks.xyn, confidences, classes):
            rows.append({"label": label_for(int(cls)), "confidence": round(float(confidence), 4), "kind": "polygon", "points": polygon.tolist()})
    elif task == "pose" and keypoints is not None:
        for points, confidence, cls in zip(keypoints.xyn.cpu().tolist(), confidences, classes):
            rows.append({"label": label_for(int(cls)), "confidence": round(float(confidence), 4), "kind": "keypoints", "points": points})
    else:
        for box, confidence, cls in zip(boxes.xyxyn.cpu().tolist(), confidences, classes):
            rows.append({"label": label_for(int(cls)), "confidence": round(float(confidence), 4), "kind": "rectangle", "points": box})
    return rows


def _annotated_data_url(result: object) -> str:
    from PIL import Image

    plotted = result.plot()
    output = io.BytesIO()
    Image.fromarray(plotted[:, :, ::-1]).save(output, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _pretrained_task(name: str) -> str:
    stem = Path(name).stem.lower()
    if stem.endswith("-seg"):
        return "segment"
    if stem.endswith("-sem"):
        return "semantic"
    if stem.endswith("-pose"):
        return "pose"
    if stem.endswith("-obb"):
        return "obb"
    return "detect"


def _pretrained_json(path: Path, root: Path) -> dict:
    can_test = bool(TESTABLE_PRETRAINED_PATTERN.fullmatch(path.name)) and path.name.lower() != "sam3.pt"
    return {
        "id": path.name,
        "name": path.name,
        "path": path.relative_to(root).as_posix(),
        "kind": "PRETRAINED",
        "task": _pretrained_task(path.name),
        "canTest": can_test,
        "sizeBytes": path.stat().st_size,
    }


def _training_quality(request: Request, artifact: ModelArtifact) -> dict:
    if artifact.training_quality_json and artifact.training_quality_json != "{}":
        try:
            return json.loads(artifact.training_quality_json)
        except json.JSONDecodeError:
            pass
    results_csv = next(iter((request.app.state.root / "runs" / artifact.training_job_id).rglob("results.csv")), None)
    return summarize_results_file(results_csv, artifact.task) if results_csv else {
        "state": "INCOMPLETE", "primaryMetric": None, "bestEpoch": None,
        "bestValue": None, "finalValue": None, "validationMetrics": {},
        "lossMetrics": {}, "notes": ["RESULTS_FILE_MISSING"],
    }


async def _validated_prediction_source(image: UploadFile, confidence: float):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(422, detail={"code": "INVALID_IMAGE", "message": "请上传图片文件"})
    if confidence < 0 or confidence > 1:
        raise HTTPException(422, detail={"code": "INVALID_CONFIDENCE", "message": "置信度必须在 0 到 1 之间"})
    payload = await image.read(MAX_PREDICT_IMAGE_BYTES + 1)
    if len(payload) > MAX_PREDICT_IMAGE_BYTES:
        raise HTTPException(413, detail={"code": "IMAGE_TOO_LARGE", "message": "图片大小不能超过 10 MB"})
    try:
        from PIL import Image
        with Image.open(io.BytesIO(payload)) as checked:
            checked.verify()
        return Image.open(io.BytesIO(payload)).convert("RGB")
    except Exception as exc:
        raise HTTPException(422, detail={"code": "INVALID_IMAGE", "message": "图片无法读取"}) from exc


def _prediction_response(
    model_path: Path,
    model_id: str,
    model_name: str,
    model_format: str,
    task: str,
    source,
    mime_type: str,
    confidence: float,
) -> dict:
    try:
        model = _get_cached_model(model_path)
        result = model.predict(source, conf=confidence, verbose=False)[0]
        predictions = _prediction_rows(result, task)
        annotated = _annotated_data_url(result)
    except Exception as exc:
        raise HTTPException(422, detail={"code": "PREDICTION_FAILED", "message": f"模型推理失败：{exc}"}) from exc
    return {"data": {
        "model": {"id": model_id, "name": model_name, "format": model_format, "task": task},
        "image": {"width": source.width, "height": source.height, "mimeType": mime_type},
        "annotatedImage": annotated,
        "predictions": predictions,
    }}


def export_json(item: ExportJob) -> dict:
    return {
        "id": item.id, "artifactId": item.artifact_id, "format": item.format,
        "status": item.status, "progress": item.progress, "params": json.loads(item.params_json),
        "outputPath": item.output_path, "errorMessage": item.error_message,
        "createdAt": item.created_at.isoformat(),
    }


def video_job_json(job: VideoInferenceJob) -> dict:
    return {
        "id": job.id, "modelId": job.model_id, "modelFormat": job.model_format, "task": job.task,
        "status": job.status, "progress": job.progress, "currentFrame": job.current_frame,
        "totalFrames": job.total_frames, "fps": job.fps, "width": job.width, "height": job.height,
        "params": json.loads(job.params_json), "errorMessage": job.error_message,
        "outputPath": job.output_path,
        "downloadUrl": f"/api/v1/models/video-jobs/{job.id}/download" if job.output_path else None,
        "createdAt": job.created_at.isoformat(), "updatedAt": job.updated_at.isoformat(),
    }


def _resolve_video_model(request: Request, model_id: str, model_format: str, session: Session) -> tuple[Path, str, str]:
    if model_id.startswith("pretrained:"):
        pretrained_id = model_id.removeprefix("pretrained:")
        if Path(pretrained_id).name != pretrained_id or "/" in pretrained_id or "\\" in pretrained_id:
            raise HTTPException(404, detail={"code": "PRETRAINED_MODEL_NOT_FOUND", "message": "预训练模型不存在"})
        pretrained_dir = (request.app.state.root / "models" / "pretrained").resolve()
        model_path = {path.name: path.resolve() for path in pretrained_dir.glob("*.pt") if path.is_file()}.get(pretrained_id)
        if not model_path:
            raise HTTPException(404, detail={"code": "PRETRAINED_MODEL_NOT_FOUND", "message": "预训练模型不存在"})
        metadata = _pretrained_json(model_path, request.app.state.root)
        if not metadata["canTest"]:
            raise HTTPException(422, detail={"code": "PRETRAINED_MODEL_NOT_TESTABLE", "message": "该预训练模型不支持推理"})
        return model_path, metadata["task"], "pt"

    artifact = session.get(ModelArtifact, model_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "MODEL_NOT_FOUND", "message": "模型产物不存在"})
    job = session.get(TrainingJob, artifact.training_job_id)
    if not job or job.status != JobStatus.SUCCEEDED:
        raise HTTPException(409, detail={"code": "MODEL_NOT_READY", "message": "只有成功完成训练的模型才能推理"})
    if model_format not in {"pt", "onnx"}:
        raise HTTPException(422, detail={"code": "INVALID_MODEL_FORMAT", "message": "模型格式只能是 PT 或 ONNX"})
    model_path = request.app.state.paths.resolve(artifact.path)
    if model_format == "onnx":
        export = session.scalar(select(ExportJob).where(
            ExportJob.artifact_id == model_id, ExportJob.format == "onnx", ExportJob.status == JobStatus.SUCCEEDED,
        ).order_by(ExportJob.created_at.desc()))
        if not export or not export.output_path:
            raise HTTPException(409, detail={"code": "ONNX_NOT_READY", "message": "ONNX 尚未导出完成"})
        model_path = request.app.state.paths.resolve(export.output_path)
    if not model_path.is_file():
        raise HTTPException(404, detail={"code": "MODEL_FILE_MISSING", "message": "模型文件缺失"})
    return model_path, artifact.task, model_format


async def _save_video_upload(upload: UploadFile, destination: Path) -> int:
    suffix = Path(upload.filename or "").suffix.lower()
    if (not upload.content_type or not upload.content_type.startswith("video/")) and suffix not in VIDEO_SUFFIXES:
        raise HTTPException(422, detail={"code": "INVALID_VIDEO", "message": "请上传 MP4、MOV、AVI、MKV 或 WebM 视频"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_PREDICT_VIDEO_BYTES:
                destination.unlink(missing_ok=True)
                raise HTTPException(413, detail={"code": "VIDEO_TOO_LARGE", "message": "视频大小不能超过 500 MB"})
            output.write(chunk)
    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(422, detail={"code": "INVALID_VIDEO", "message": "视频文件为空"})
    return size


@router.get("")
def list_models(request: Request, session: Session = Depends(get_session)) -> dict:
    artifacts = [{
        "id": item.id, "trainingJobId": item.training_job_id, "name": item.name, "task": item.task, "path": item.path,
        "kind": item.kind, "sha256": item.sha256, "metrics": json.loads(item.metrics_json),
        "trainingQuality": _training_quality(request, item),
    } for item in session.scalars(select(ModelArtifact).order_by(ModelArtifact.created_at.desc()))]
    pretrained = []
    for path in sorted((request.app.state.root / "models" / "pretrained").glob("*.pt")):
        pretrained.append(_pretrained_json(path, request.app.state.root))
    return {"data": artifacts, "pretrained": pretrained}


@router.post("/video-jobs", status_code=status.HTTP_201_CREATED)
async def create_video_job(
    request: Request,
    video: UploadFile = File(...),
    model_id: str = Form(..., alias="modelId"),
    confidence: float = Form(default=0.25),
    model_format: str = Form(default="pt", alias="format"),
    session: Session = Depends(get_session),
) -> dict:
    if confidence < 0 or confidence > 1:
        raise HTTPException(422, detail={"code": "INVALID_CONFIDENCE", "message": "置信度必须在 0 到 1 之间"})
    model_path, task, resolved_format = _resolve_video_model(request, model_id, model_format, session)
    job_id = str(uuid4())
    input_path = request.app.state.root / "runs" / "video-inference" / job_id / f"input{Path(video.filename or '.mp4').suffix.lower() or '.mp4'}"
    await _save_video_upload(video, input_path)
    job = VideoInferenceJob(
        id=job_id, model_id=model_id, model_path=request.app.state.paths.relative(model_path),
        model_format=resolved_format, task=task, input_path=request.app.state.paths.relative(input_path),
        output_path=f"runs/video-inference/{job_id}/output.mp4", status=JobStatus.QUEUED,
        params_json=json.dumps({"confidence": confidence, "sourceName": video.filename or input_path.name}, ensure_ascii=False),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return video_job_json(job)


@router.get("/video-jobs/{job_id}")
def get_video_job(job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(VideoInferenceJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "VIDEO_JOB_NOT_FOUND", "message": "视频任务不存在"})
    return video_job_json(job)


@router.post("/video-jobs/{job_id}/cancel")
def cancel_video_job(job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(VideoInferenceJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "VIDEO_JOB_NOT_FOUND", "message": "视频任务不存在"})
    if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
        job.status = JobStatus.CANCELLED
        session.commit()
    return video_job_json(job)


@router.get("/video-jobs/{job_id}/download")
def download_video_job(job_id: str, request: Request, session: Session = Depends(get_session)) -> FileResponse:
    job = session.get(VideoInferenceJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "VIDEO_JOB_NOT_FOUND", "message": "视频任务不存在"})
    if job.status != JobStatus.SUCCEEDED or not job.output_path:
        raise HTTPException(409, detail={"code": "VIDEO_NOT_READY", "message": "视频结果尚未生成"})
    path = request.app.state.paths.resolve(job.output_path)
    if not path.is_file():
        raise HTTPException(404, detail={"code": "VIDEO_OUTPUT_MISSING", "message": "视频结果文件缺失"})
    return FileResponse(path, filename=f"{job.id}.mp4", media_type="video/mp4")


@router.delete("/{artifact_id}")
def delete_model_artifact(artifact_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    artifact = session.get(ModelArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "MODEL_NOT_FOUND", "message": "模型产物不存在"})

    exports = list(session.scalars(select(ExportJob).where(ExportJob.artifact_id == artifact_id)))
    if any(export.status == JobStatus.RUNNING for export in exports):
        raise HTTPException(409, detail={"code": "EXPORT_RUNNING", "message": "ONNX 正在导出，请完成或停止导出后再删除"})

    artifact_path = request.app.state.paths.resolve(artifact.path)
    artifact_path.unlink(missing_ok=True)
    for export in exports:
        if export.output_path:
            request.app.state.paths.resolve(export.output_path).unlink(missing_ok=True)
        shutil.rmtree(request.app.state.root / "runs" / "exports" / export.id, ignore_errors=True)
        session.delete(export)

    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.pop(str(artifact_path), None)
    session.delete(artifact)
    session.commit()
    return {"id": artifact_id, "deleted": True}


@router.get("/{artifact_id}/download")
def download_model(request: Request, artifact_id: str, session: Session = Depends(get_session)) -> FileResponse:
    artifact = session.get(ModelArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "MODEL_NOT_FOUND", "message": "模型产物不存在"})
    path = request.app.state.paths.resolve(artifact.path)
    if not path.is_file():
        raise HTTPException(404, detail={"code": "MODEL_FILE_MISSING", "message": "模型文件缺失"})
    return FileResponse(path, filename=artifact.name, media_type="application/octet-stream")


@router.get("/{artifact_id}/onnx/download")
def download_onnx(request: Request, artifact_id: str, session: Session = Depends(get_session)) -> FileResponse:
    export = session.scalar(select(ExportJob).where(
        ExportJob.artifact_id == artifact_id,
        ExportJob.format == "onnx",
        ExportJob.status == JobStatus.SUCCEEDED,
    ).order_by(ExportJob.created_at.desc()))
    if not export or not export.output_path:
        raise HTTPException(404, detail={"code": "ONNX_NOT_READY", "message": "ONNX 尚未生成完成"})
    path = request.app.state.paths.resolve(export.output_path)
    if not path.is_file():
        raise HTTPException(404, detail={"code": "ONNX_FILE_MISSING", "message": "ONNX 文件不存在"})
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.post("/{artifact_id}/predict")
async def predict_model(
    request: Request,
    artifact_id: str,
    image: UploadFile = File(...),
    confidence: float = Form(default=0.25),
    model_format: str = Form(default="pt", alias="format"),
    session: Session = Depends(get_session),
) -> dict:
    artifact = session.get(ModelArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "MODEL_NOT_FOUND", "message": "模型产物不存在"})
    job = session.get(TrainingJob, artifact.training_job_id)
    if not job or job.status != JobStatus.SUCCEEDED:
        raise HTTPException(409, detail={"code": "MODEL_NOT_READY", "message": "只有成功完成训练的模型才能测试"})
    if model_format not in {"pt", "onnx"}:
        raise HTTPException(422, detail={"code": "INVALID_MODEL_FORMAT", "message": "模型格式只能是 PT 或 ONNX"})
    model_path = request.app.state.paths.resolve(artifact.path)
    model_name = artifact.name
    if model_format == "onnx":
        export = session.scalar(select(ExportJob).where(
            ExportJob.artifact_id == artifact_id,
            ExportJob.format == "onnx",
            ExportJob.status == JobStatus.SUCCEEDED,
        ).order_by(ExportJob.created_at.desc()))
        if not export or not export.output_path:
            raise HTTPException(409, detail={"code": "ONNX_NOT_READY", "message": "ONNX 尚未导出完成"})
        model_path = request.app.state.paths.resolve(export.output_path)
        model_name = model_path.name
    if not model_path.is_file():
        raise HTTPException(404, detail={"code": "MODEL_FILE_MISSING", "message": "模型文件缺失"})
    source = await _validated_prediction_source(image, confidence)
    return _prediction_response(model_path, artifact.id, model_name, model_format, artifact.task, source, image.content_type, confidence)


@router.post("/pretrained/{model_id}/predict")
async def predict_pretrained_model(
    request: Request,
    model_id: str,
    image: UploadFile = File(...),
    confidence: float = Form(default=0.25),
) -> dict:
    if Path(model_id).name != model_id or "/" in model_id or "\\" in model_id:
        raise HTTPException(404, detail={"code": "PRETRAINED_MODEL_NOT_FOUND", "message": "预训练模型不存在"})
    pretrained_dir = (request.app.state.root / "models" / "pretrained").resolve()
    allowed = {path.name: path.resolve() for path in pretrained_dir.glob("*.pt") if path.is_file()}
    model_path = allowed.get(model_id)
    if not model_path or model_path.parent != pretrained_dir:
        raise HTTPException(404, detail={"code": "PRETRAINED_MODEL_NOT_FOUND", "message": "预训练模型不存在"})
    metadata = _pretrained_json(model_path, request.app.state.root)
    if not metadata["canTest"]:
        raise HTTPException(422, detail={"code": "PRETRAINED_MODEL_NOT_TESTABLE", "message": "该预训练模型不支持无提示词单图测试"})
    source = await _validated_prediction_source(image, confidence)
    return _prediction_response(model_path, model_id, model_id, "pt", metadata["task"], source, image.content_type, confidence)


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
