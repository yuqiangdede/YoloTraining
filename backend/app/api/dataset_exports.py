import json
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Dataset, DatasetExportJob, DatasetVersion
from app.schemas.common import ApiModel
from app.services.state_machine import JobStatus


router = APIRouter(prefix="/datasets", tags=["dataset-exports"])


class DatasetExportCreate(ApiModel):
    format: str = Field(pattern="^(yolo|coco|voc|platform_json)$")


def export_json(item: DatasetExportJob) -> dict:
    return {"id": item.id, "datasetId": item.dataset_id, "versionId": item.version_id, "format": item.format,
            "status": item.status, "outputPath": item.output_path, "errorMessage": item.error_message,
            "createdAt": item.created_at.isoformat()}


def _coco(manifest: dict) -> dict:
    categories = [{"id": index + 1, "name": item["name"]} for index, item in enumerate(manifest.get("classes", []))]
    category_by_id = {item["id"]: index + 1 for index, item in enumerate(manifest.get("classes", []))}
    images, annotations = [], []
    for index, (asset_id, document) in enumerate(manifest.get("annotations", {}).items(), start=1):
        images.append({"id": index, "file_name": f"{asset_id}.jpg", "width": document["imageWidth"], "height": document["imageHeight"]})
        for shape_index, shape in enumerate(document.get("shapes", []), start=1):
            points = shape.get("points", [])
            xs = [point[0] * document["imageWidth"] for point in points]
            ys = [point[1] * document["imageHeight"] for point in points]
            if not xs:
                continue
            x, y, width, height = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
            annotations.append({"id": len(annotations) + 1, "image_id": index, "category_id": category_by_id.get(shape["labelId"], 0), "bbox": [x, y, width, height], "area": width * height, "iscrowd": 0, "segmentation": [sum(points, [])]})
    return {"images": images, "annotations": annotations, "categories": categories}


def _write_archive(root: Path, version: DatasetVersion, fmt: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(version.manifest_json)
    if fmt == "yolo":
        shutil.make_archive(str(output.with_suffix("")), "zip", root / version.snapshot_path)
        return
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        if fmt == "platform_json":
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        elif fmt == "coco":
            archive.writestr("annotations.json", json.dumps(_coco(manifest), ensure_ascii=False, indent=2))
        else:
            for asset_id, document in manifest.get("annotations", {}).items():
                archive.writestr(f"Annotations/{asset_id}.xml", f"<annotation><filename>{asset_id}</filename><size><width>{document['imageWidth']}</width><height>{document['imageHeight']}</height></size></annotation>")


@router.post("/{dataset_id}/versions/{version_id}/exports", status_code=status.HTTP_201_CREATED)
def create_dataset_export(dataset_id: str, version_id: str, request: Request, payload: DatasetExportCreate, session: Session = Depends(get_session)) -> dict:
    if not session.get(Dataset, dataset_id):
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "Dataset not found"})
    version = session.get(DatasetVersion, version_id)
    if not version or version.dataset_id != dataset_id:
        raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND", "message": "Dataset version not found"})
    job = DatasetExportJob(id=str(uuid4()), dataset_id=dataset_id, version_id=version_id, format=payload.format, status=JobStatus.RUNNING)
    session.add(job)
    session.commit()
    try:
        relative = Path("runs") / "dataset-exports" / job.id / f"{version.name}.{payload.format}.zip"
        _write_archive(request.app.state.root, version, payload.format, request.app.state.root / relative)
        job.output_path = relative.as_posix()
        job.status = JobStatus.SUCCEEDED
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
    session.commit()
    return export_json(job)


@router.get("/{dataset_id}/exports")
def list_dataset_exports(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    if not session.get(Dataset, dataset_id):
        raise HTTPException(404, detail={"code": "DATASET_NOT_FOUND", "message": "Dataset not found"})
    return {"data": [export_json(item) for item in session.scalars(select(DatasetExportJob).where(DatasetExportJob.dataset_id == dataset_id).order_by(DatasetExportJob.created_at.desc()))]}


@router.get("/{dataset_id}/exports/{export_id}/download")
def download_dataset_export(dataset_id: str, export_id: str, request: Request, session: Session = Depends(get_session)) -> FileResponse:
    item = session.get(DatasetExportJob, export_id)
    if not item or item.dataset_id != dataset_id or item.status != JobStatus.SUCCEEDED or not item.output_path:
        raise HTTPException(404, detail={"code": "DATASET_EXPORT_NOT_READY", "message": "Dataset export is not ready"})
    path = request.app.state.paths.resolve(item.output_path)
    if not path.is_file():
        raise HTTPException(404, detail={"code": "DATASET_EXPORT_FILE_MISSING", "message": "Dataset export file is missing"})
    return FileResponse(path, filename=path.name, media_type="application/zip")
