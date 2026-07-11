import json

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import DatasetVersion
from app.schemas.datasets import DatasetCreate
from app.services.dataset_builder import create_snapshot


router = APIRouter(prefix="/datasets", tags=["datasets"])


def dataset_json(item: DatasetVersion) -> dict:
    return {
        "id": item.id, "name": item.name, "task": item.task, "snapshotPath": item.snapshot_path,
        "contentHash": item.content_hash, "assetCount": item.asset_count,
        "manifest": json.loads(item.manifest_json), "createdAt": item.created_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_dataset(request: Request, payload: DatasetCreate, session: Session = Depends(get_session)) -> dict:
    return dataset_json(create_snapshot(session, request.app.state.root, payload))


@router.get("")
def list_datasets(session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(DatasetVersion).order_by(DatasetVersion.created_at.desc()))
    return {"data": [dataset_json(item) for item in items]}
