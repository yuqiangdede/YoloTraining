import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Annotation, Asset, Dataset, DatasetCategory, DatasetVersion, ExportJob, ModelArtifact, Project, TrainingJob
from app.schemas.imports import VocImportRequest
from app.schemas.datasets import DatasetCategoryCreate, DatasetCreate, DatasetUpdate, DatasetVersionCreate
from app.services.dataset_builder import DatasetSplitError, create_snapshot
from app.services.dataset_quality import run_quality_check
from app.services.voc_importer import VocImportError, import_voc_dataset


router = APIRouter(prefix="/datasets", tags=["datasets"])
COLORS = ["#e36a22", "#237a57", "#3267c8", "#a650b5", "#b84336", "#9b6415"]


def category_json(item: DatasetCategory) -> dict:
    return {"id": item.id, "name": item.name, "color": item.color}


def dataset_json(item: Dataset, session: Session) -> dict:
    categories = session.scalars(select(DatasetCategory).where(DatasetCategory.dataset_id == item.id).order_by(DatasetCategory.created_at))
    annotation_statuses = list(session.scalars(
        select(Annotation.status).select_from(Asset).outerjoin(Annotation, Annotation.asset_id == Asset.id)
        .where(Asset.dataset_id == item.id, Asset.is_deleted.is_(False))
    ))
    asset_count = len(annotation_statuses)
    annotation_counts = {
        "unlabeled": sum(status is None for status in annotation_statuses),
        "draft": sum(status == "DRAFT" for status in annotation_statuses),
        "completed": sum(status == "COMPLETED" for status in annotation_statuses),
        "reviewed": sum(status == "REVIEWED" for status in annotation_statuses),
    }
    return {
        "id": item.id, "projectId": item.project_id, "name": item.name, "task": item.task, "assetCount": asset_count,
        "annotationCounts": annotation_counts,
        "categories": [category_json(category) for category in categories],
        "keypointCount": item.keypoint_count, "flipIdx": json.loads(item.flip_idx_json) if item.flip_idx_json else None,
        "prelabelModelPath": item.prelabel_model_path, "prelabelMode": item.prelabel_mode,
        "prelabelConfidence": item.prelabel_confidence,
        "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat(),
    }


def version_json(item: DatasetVersion) -> dict:
    return {"id": item.id, "datasetId": item.dataset_id, "name": item.name, "task": item.task,
            "snapshotPath": item.snapshot_path, "contentHash": item.content_hash,
            "assetCount": item.asset_count, "manifest": json.loads(item.manifest_json),
            "parentVersionId": item.parent_version_id, "quality": json.loads(item.quality_report_json or "{}"),
            "source": json.loads(item.source_json or "{}"), "createdAt": item.created_at.isoformat()}


def require_dataset(dataset_id: str, session: Session) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "数据集不存在"})
    return dataset


@router.post("", status_code=status.HTTP_201_CREATED)
def create_dataset(payload: DatasetCreate, session: Session = Depends(get_session)) -> dict:
    if not session.get(Project, payload.project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    dataset = Dataset(id=str(uuid4()), project_id=payload.project_id, name=payload.name, task=payload.task, keypoint_count=payload.keypoint_count,
                      flip_idx_json=json.dumps(payload.flip_idx) if payload.flip_idx is not None else None)
    session.add(dataset)
    for index, category in enumerate(payload.categories):
        session.add(DatasetCategory(id=str(uuid4()), dataset_id=dataset.id, name=category.name, color=COLORS[index % len(COLORS)]))
    try:
        session.commit()
    except Exception as error:
        session.rollback()
        raise HTTPException(409, detail={"code": "DATASET_NAME_EXISTS", "message": "数据集名称已存在"}) from error
    return {"data": dataset_json(dataset, session)}


@router.get("")
def list_datasets(project_id: str | None = None, session: Session = Depends(get_session)) -> dict:
    query = select(Dataset).order_by(Dataset.created_at.desc())
    if project_id:
        query = query.where(Dataset.project_id == project_id)
    return {"data": [dataset_json(item, session) for item in session.scalars(query)]}


@router.get("/versions/all")
def list_all_dataset_versions(session: Session = Depends(get_session)) -> dict:
    return {"data": [version_json(item) for item in session.scalars(select(DatasetVersion).order_by(DatasetVersion.created_at.desc()))]}


@router.post("/imports/voc", status_code=status.HTTP_201_CREATED)
def import_voc(request: Request, payload: VocImportRequest, session: Session = Depends(get_session)) -> dict:
    source = Path(payload.source_path).expanduser()
    name = (payload.name or source.name).strip()
    if not name:
        raise HTTPException(422, detail={"code": "INVALID_DATASET_NAME", "message": "无法从源目录推导数据集名称"})
    try:
        dataset, version, report = import_voc_dataset(
            session, request.app.state.root, payload.source_path, name, payload.train_ratio, payload.val_ratio, payload.seed,
        )
    except VocImportError as error:
        code = 409 if error.code == "DATASET_NAME_EXISTS" else 422
        raise HTTPException(code, detail={"code": error.code, "message": error.message, "details": error.details}) from error
    return {"data": {"dataset": dataset_json(dataset, session), "version": version_json(version), "report": report}}


@router.get("/{dataset_id}")
def get_dataset(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    return {"data": dataset_json(require_dataset(dataset_id, session), session)}


@router.get("/{dataset_id}/summary")
def dataset_summary(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    dataset = require_dataset(dataset_id, session)
    return {"data": {"dataset": dataset_json(dataset, session), "quality": run_quality_check(session, dataset), "versions": session.scalar(select(__import__("sqlalchemy").func.count()).select_from(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)) or 0}}


@router.get("/{dataset_id}/quality")
def dataset_quality(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    return {"data": run_quality_check(session, require_dataset(dataset_id, session))}


@router.post("/{dataset_id}/quality/check")
def check_dataset_quality(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    return {"data": run_quality_check(session, require_dataset(dataset_id, session))}


@router.patch("/{dataset_id}")
def update_dataset(dataset_id: str, payload: DatasetUpdate, session: Session = Depends(get_session)) -> dict:
    dataset = require_dataset(dataset_id, session)
    dataset.name = payload.name
    dataset.prelabel_model_path = payload.prelabel_model_path
    dataset.prelabel_mode = payload.prelabel_mode
    dataset.prelabel_confidence = payload.prelabel_confidence
    session.commit()
    return {"data": dataset_json(dataset, session)}


@router.get("/{dataset_id}/categories")
def list_categories(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    return {"data": [category_json(item) for item in session.scalars(select(DatasetCategory).where(DatasetCategory.dataset_id == dataset_id).order_by(DatasetCategory.created_at))]}


@router.post("/{dataset_id}/categories", status_code=status.HTTP_201_CREATED)
def create_category(dataset_id: str, payload: DatasetCategoryCreate, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    name = payload.name.strip()
    duplicate = session.scalar(select(DatasetCategory).where(DatasetCategory.dataset_id == dataset_id, __import__("sqlalchemy").func.lower(DatasetCategory.name) == name.casefold()))
    if duplicate:
        raise HTTPException(409, detail={"code": "CATEGORY_NAME_EXISTS", "message": "类别名称已存在"})
    index = session.scalar(select(__import__("sqlalchemy").func.count()).select_from(DatasetCategory).where(DatasetCategory.dataset_id == dataset_id)) or 0
    category = DatasetCategory(id=str(uuid4()), dataset_id=dataset_id, name=name, color=COLORS[index % len(COLORS)])
    session.add(category); session.commit()
    return {"data": category_json(category)}


@router.delete("/{dataset_id}/categories/{category_id}")
def delete_category(dataset_id: str, category_id: str, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    category = session.get(DatasetCategory, category_id)
    if not category or category.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "CATEGORY_NOT_FOUND", "message": "类别不存在"})
    references = list(session.scalars(select(Annotation).join(Asset, Annotation.asset_id == Asset.id).where(Asset.dataset_id == dataset_id)))
    for annotation in references:
        document = json.loads(annotation.document_json)
        shapes = document.get("shapes", [])
        filtered = [shape for shape in shapes if shape.get("labelId") != category_id]
        if len(filtered) == len(shapes):
            continue
        document["shapes"] = filtered
        annotation.document_json = json.dumps(document, ensure_ascii=False)
        annotation.version += 1
    session.delete(category); session.commit()
    return {"id": category_id, "deleted": True}


@router.patch("/{dataset_id}/categories/{category_id}")
def update_category(dataset_id: str, category_id: str, payload: DatasetCategoryCreate, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    category = session.get(DatasetCategory, category_id)
    if not category or category.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "CATEGORY_NOT_FOUND", "message": "类别不存在"})
    name = payload.name.strip()
    duplicate = session.scalar(select(DatasetCategory).where(DatasetCategory.dataset_id == dataset_id, DatasetCategory.id != category_id, __import__("sqlalchemy").func.lower(DatasetCategory.name) == name.casefold()))
    if duplicate:
        raise HTTPException(409, detail={"code": "CATEGORY_NAME_EXISTS", "message": "类别名称已存在"})
    category.name = name
    session.commit()
    return {"data": category_json(category)}


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    version_ids = list(session.scalars(select(DatasetVersion.id).where(DatasetVersion.dataset_id == dataset_id)))
    jobs = list(session.scalars(select(TrainingJob).where(TrainingJob.dataset_version_id.in_(version_ids)))) if version_ids else []
    artifact_job_ids = set(session.scalars(select(ModelArtifact.training_job_id)))
    if jobs or any(job.id in artifact_job_ids for job in jobs):
        raise HTTPException(409, detail={"code": "DATASET_IN_USE", "message": "数据集已有训练任务或模型产物，不能删除"})
    assets = list(session.scalars(select(Asset).where(Asset.dataset_id == dataset_id)))
    for asset in assets:
        (request.app.state.root / asset.storage_path).unlink(missing_ok=True)
    for version in session.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)):
        shutil.rmtree(request.app.state.root / version.snapshot_path, ignore_errors=True)
    session.query(Annotation).filter(Annotation.asset_id.in_([item.id for item in assets])).delete(synchronize_session=False)
    session.query(Asset).filter(Asset.dataset_id == dataset_id).delete(synchronize_session=False)
    session.query(DatasetCategory).filter(DatasetCategory.dataset_id == dataset_id).delete(synchronize_session=False)
    session.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id).delete(synchronize_session=False)
    session.delete(require_dataset(dataset_id, session)); session.commit()
    return {"id": dataset_id, "deleted": True}


@router.post("/{dataset_id}/versions", status_code=status.HTTP_201_CREATED)
def create_dataset_version(dataset_id: str, request: Request, payload: DatasetVersionCreate, session: Session = Depends(get_session)) -> dict:
    try:
        return version_json(create_snapshot(session, request.app.state.root, require_dataset(dataset_id, session), payload))
    except DatasetSplitError as error:
        raise HTTPException(422, detail={"code": "INVALID_DATASET_SPLIT", "message": str(error)}) from error


@router.get("/{dataset_id}/versions")
def list_dataset_versions(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    return {"data": [version_json(item) for item in session.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id).order_by(DatasetVersion.created_at.desc()))]}


@router.get("/{dataset_id}/versions/{version_id}")
def get_dataset_version(dataset_id: str, version_id: str, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    version = session.get(DatasetVersion, version_id)
    if not version or version.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND", "message": "Dataset version not found"})
    return {"data": version_json(version)}


@router.post("/{dataset_id}/versions/{version_id}/copy", status_code=status.HTTP_201_CREATED)
def copy_dataset_version(dataset_id: str, version_id: str, request: Request, payload: DatasetVersionCreate, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    source = session.get(DatasetVersion, version_id)
    if not source or source.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND", "message": "Dataset version not found"})
    payload.parent_version_id = version_id
    try:
        copied = create_snapshot(session, request.app.state.root, require_dataset(dataset_id, session), payload)
    except DatasetSplitError as error:
        raise HTTPException(422, detail={"code": "INVALID_DATASET_SPLIT", "message": str(error)}) from error
    return {"data": version_json(copied)}


@router.delete("/{dataset_id}/versions/{version_id}")
def delete_dataset_version(dataset_id: str, version_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    require_dataset(dataset_id, session)
    version = session.get(DatasetVersion, version_id)
    if not version or version.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND", "message": "数据集训练版本不存在"})
    jobs = list(session.scalars(select(TrainingJob).where(TrainingJob.dataset_version_id == version_id)))
    if any(job.status in {"RUNNING", "PAUSING"} for job in jobs):
        raise HTTPException(409, detail={"code": "VERSION_IN_USE", "message": "训练中的任务请先取消后再删除数据集版本"})
    for job in jobs:
        artifacts = list(session.scalars(select(ModelArtifact).where(ModelArtifact.training_job_id == job.id)))
        artifact_ids = [item.id for item in artifacts]
        exports = list(session.scalars(select(ExportJob).where(ExportJob.artifact_id.in_(artifact_ids)))) if artifact_ids else []
        for artifact in artifacts:
            request.app.state.paths.resolve(artifact.path).unlink(missing_ok=True)
        for export in exports:
            if export.output_path:
                request.app.state.paths.resolve(export.output_path).unlink(missing_ok=True)
            shutil.rmtree(request.app.state.root / "runs" / "exports" / export.id, ignore_errors=True)
        if artifact_ids:
            session.query(ExportJob).filter(ExportJob.artifact_id.in_(artifact_ids)).delete(synchronize_session=False)
        session.query(ModelArtifact).filter(ModelArtifact.training_job_id == job.id).delete(synchronize_session=False)
        shutil.rmtree(request.app.state.root / job.run_path, ignore_errors=True)
    session.query(TrainingJob).filter(TrainingJob.dataset_version_id == version_id).delete(synchronize_session=False)
    shutil.rmtree(request.app.state.root / version.snapshot_path, ignore_errors=True)
    session.delete(version)
    session.commit()
    return {"id": version_id, "deleted": True}
