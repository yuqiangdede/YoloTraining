from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class AnnotationTaskCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    assignee: str = Field(default="", max_length=100)
    asset_ids: list[str] | None = None


class AnnotationTaskUpdate(ApiModel):
    assignee: str = Field(default="", max_length=100)
    status: Literal["NEW", "IN_PROGRESS", "COMPLETED"]
