from pydantic import Field

from app.schemas.common import ApiModel


class CategoryCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
