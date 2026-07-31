from pydantic import Field

from app.schemas.common import ApiModel


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
