from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Dataset, DatasetVersion, ModelArtifact, Project, TrainingJob
from app.schemas.projects import ProjectCreate


router = APIRouter(prefix="/projects", tags=["projects"])


def project_json(item: Project, session: Session) -> dict:
    dataset_ids = select(Dataset.id).where(Dataset.project_id == item.id)
    version_ids = select(DatasetVersion.id).where(DatasetVersion.dataset_id.in_(dataset_ids))
    job_ids = select(TrainingJob.id).where(TrainingJob.dataset_version_id.in_(version_ids))
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "datasetCount": session.scalar(select(func.count()).select_from(Dataset).where(Dataset.project_id == item.id)) or 0,
        "trainingCount": session.scalar(select(func.count()).select_from(TrainingJob).where(TrainingJob.dataset_version_id.in_(version_ids))) or 0,
        "modelCount": session.scalar(select(func.count()).select_from(ModelArtifact).where(ModelArtifact.training_job_id.in_(job_ids))) or 0,
        "createdAt": item.created_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
    }


def require_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    return project


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)) -> dict:
    project = Project(id=str(uuid4()), name=payload.name.strip(), description=payload.description.strip())
    session.add(project)
    try:
        session.commit()
    except Exception as error:
        session.rollback()
        raise HTTPException(409, detail={"code": "PROJECT_NAME_EXISTS", "message": "项目名称已存在"}) from error
    return {"data": project_json(project, session)}


@router.get("")
def list_projects(session: Session = Depends(get_session)) -> dict:
    projects = session.scalars(select(Project).order_by(Project.created_at.asc()))
    return {"data": [project_json(item, session) for item in projects]}


@router.get("/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    return {"data": project_json(require_project(project_id, session), session)}


@router.delete("/{project_id}")
def delete_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    if project_id == "default":
        raise HTTPException(409, detail={"code": "DEFAULT_PROJECT_PROTECTED", "message": "默认项目不可删除"})
    has_datasets = select(Dataset.id).where(Dataset.project_id == project_id).exists()
    deleted = session.execute(delete(Project).where(Project.id == project_id, ~has_datasets)).rowcount
    if not deleted:
        require_project(project_id, session)
        raise HTTPException(409, detail={"code": "PROJECT_NOT_EMPTY", "message": "项目仍有数据集，请先到数据集页面处理"})
    session.commit()
    return {"id": project_id, "deleted": True}
