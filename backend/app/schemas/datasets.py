from pydantic import Field, model_validator

from app.schemas.annotations import TaskType
from app.schemas.common import ApiModel


class DatasetClass(ApiModel):
    id: str
    name: str


class DatasetCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    task: TaskType
    asset_ids: list[str] = Field(min_length=1)
    classes: list[DatasetClass] = Field(min_length=1)
    train_ratio: float = Field(default=0.8, ge=0, le=1)
    val_ratio: float = Field(default=0.2, ge=0, le=1)
    test_ratio: float = Field(default=0.0, ge=0, le=1)
    seed: int = 0
    keypoint_count: int | None = Field(default=None, ge=1, le=1000)
    flip_idx: list[int] | None = None

    @model_validator(mode="after")
    def ratios_total_one(self) -> "DatasetCreate":
        if abs(self.train_ratio + self.val_ratio + self.test_ratio - 1) > 1e-6:
            raise ValueError("训练、验证和测试比例之和必须为 1")
        if len({item.id for item in self.classes}) != len(self.classes):
            raise ValueError("类别 ID 不能重复")
        if self.task == TaskType.POSE:
            if not self.keypoint_count:
                raise ValueError("姿态数据集必须指定关键点数量")
            if self.flip_idx is not None and len(self.flip_idx) != self.keypoint_count:
                raise ValueError("左右翻转索引数量必须等于关键点数量")
        return self
