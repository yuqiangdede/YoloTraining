import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models import Annotation, Category
from app.schemas.categories import CategoryCreate, CategoryUpdate


router = APIRouter(prefix="/categories", tags=["categories"])
COLORS = ["#e36a22", "#237a57", "#3267c8", "#a650b5", "#b84336", "#9b6415"]


def category_json(category: Category) -> dict:
    return {"id": category.id, "name": category.name, "color": category.color, "createdAt": category.created_at.isoformat()}


def next_category_id(session: Session) -> str:
    used = {int(item) for item in session.scalars(select(Category.id)) if item.isdigit()}
    candidate = 0
    while candidate in used:
        candidate += 1
    return str(candidate)


@router.get("")
def list_categories(session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(Category)).all()
    return {"data": sorted((category_json(item) for item in items), key=lambda item: int(item["id"]))}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, session: Session = Depends(get_session)) -> dict:
    if session.scalar(select(Category).where(Category.name == payload.name.strip())):
        raise HTTPException(409, detail={"code": "CATEGORY_NAME_EXISTS", "message": "类别名称已存在"})
    category_id = next_category_id(session)
    item = Category(id=category_id, name=payload.name.strip(), color=COLORS[int(category_id) % len(COLORS)])
    session.add(item); session.commit()
    return {"data": category_json(item)}


@router.patch("/{category_id}")
def update_category(category_id: str, payload: CategoryUpdate, session: Session = Depends(get_session)) -> dict:
    item = session.get(Category, category_id)
    if not item:
        raise HTTPException(404, detail={"code": "CATEGORY_NOT_FOUND", "message": "类别不存在"})
    duplicate = session.scalar(select(Category).where(Category.name == payload.name.strip(), Category.id != category_id))
    if duplicate:
        raise HTTPException(409, detail={"code": "CATEGORY_NAME_EXISTS", "message": "类别名称已存在"})
    item.name = payload.name.strip(); session.commit()
    return {"data": category_json(item)}


@router.delete("/{category_id}")
def delete_category(category_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(Category, category_id)
    if not item:
        raise HTTPException(404, detail={"code": "CATEGORY_NOT_FOUND", "message": "类别不存在"})
    references = sum(
        1 for annotation in session.scalars(select(Annotation))
        for shape in json.loads(annotation.document_json).get("shapes", [])
        if shape.get("labelId") == category_id
    )
    if references:
        raise HTTPException(409, detail={"code": "CATEGORY_IN_USE", "message": "类别正在被标注使用", "details": {"referenceCount": references}})
    session.delete(item); session.commit()
    return {"id": category_id}
