from pydantic import Field, model_validator

from app.schemas.annotations import TaskType
from typing import Literal
from app.schemas.common import ApiModel


class DatasetCategoryCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)


class DatasetCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    project_id: str = Field(default="default", min_length=1, max_length=36)
    task: TaskType
    categories: list[DatasetCategoryCreate] = Field(min_length=1)
    keypoint_count: int | None = Field(default=None, ge=1, le=1000)
    flip_idx: list[int] | None = None

    @model_validator(mode="after")
    def validate_task_settings(self) -> "DatasetCreate":
        if len({item.name.casefold() for item in self.categories}) != len(self.categories):
            raise ValueError("类别名称不能重复")
        if self.task == TaskType.POSE and not self.keypoint_count:
            raise ValueError("姿态数据集必须指定关键点数量")
        if self.flip_idx is not None and len(self.flip_idx) != self.keypoint_count:
            raise ValueError("左右翻转索引数量必须等于关键点数量")
        return self


class DatasetUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    prelabel_model_path: str | None = Field(default=None, max_length=500)
    prelabel_mode: Literal["yolo", "yolo_sam", "sam"] = "yolo"
    prelabel_confidence: float = Field(default=0.25, ge=0, le=1)


class DatasetVersionCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    train_ratio: float = Field(default=0.8, ge=0, le=1)
    val_ratio: float = Field(default=0.2, ge=0, le=1)
    test_ratio: float = Field(default=0.0, ge=0, le=1)
    seed: int = 0
    parent_version_id: str | None = None
    @model_validator(mode="after")
    def ratios_total_one(self) -> "DatasetVersionCreate":
        if abs(self.train_ratio + self.val_ratio + self.test_ratio - 1) > 1e-6:
            raise ValueError("训练、验证和测试比例之和必须为 1")
        return self
