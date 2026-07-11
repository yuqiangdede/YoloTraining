from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import ApiModel


class TaskType(StrEnum):
    DETECT = "detect"
    SEGMENT = "segment"
    SEMANTIC = "semantic"
    POSE = "pose"
    OBB = "obb"


ShapeKind = Literal["rectangle", "polygon", "mask", "keypoints", "obb"]

TASK_SHAPES: dict[TaskType, set[str]] = {
    TaskType.DETECT: {"rectangle"},
    TaskType.SEGMENT: {"polygon"},
    TaskType.SEMANTIC: {"polygon", "mask"},
    TaskType.POSE: {"keypoints"},
    TaskType.OBB: {"obb"},
}


class AnnotationShape(ApiModel):
    id: str
    label_id: str
    kind: ShapeKind
    points: list[list[float]]
    rotation: float | None = None
    visibility: list[int] | None = None
    mask_path: str | None = None

    @model_validator(mode="after")
    def validate_geometry(self) -> "AnnotationShape":
        if any(len(point) != 2 for point in self.points):
            raise ValueError("每个点必须包含 x、y 两个坐标")
        if any(value < 0 or value > 1 for point in self.points for value in point):
            raise ValueError("坐标必须归一化到 0..1")
        minimum = {"rectangle": 2, "obb": 2, "polygon": 3, "keypoints": 1, "mask": 0}
        if len(self.points) < minimum[self.kind]:
            raise ValueError("标注点数量不足")
        if self.kind == "obb" and self.rotation is None:
            raise ValueError("旋转框必须包含角度")
        if self.kind == "mask" and not self.mask_path:
            raise ValueError("像素掩码必须包含项目内路径")
        if self.visibility is not None and len(self.visibility) != len(self.points):
            raise ValueError("关键点可见性数量必须与点数量一致")
        return self


class AnnotationDocument(ApiModel):
    asset_id: str
    task: TaskType
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    status: Literal["UNLABELED", "DRAFT", "COMPLETED", "REVIEWED"] = "DRAFT"
    shapes: list[AnnotationShape] = []

    @model_validator(mode="after")
    def validate_task_shapes(self) -> "AnnotationDocument":
        allowed = TASK_SHAPES[self.task]
        if any(shape.kind not in allowed for shape in self.shapes):
            raise ValueError(f"{self.task} 不支持当前标注形状")
        return self
