from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import ApiModel
from app.services.augmentation_presets import AugmentationPreset


TrainingTask = Literal["detect", "segment", "semantic", "pose", "obb"]
TASK_MODEL_SUFFIX: dict[str, str] = {
    "detect": ".pt",
    "segment": "-seg.pt",
    "semantic": "-sem.pt",
    "pose": "-pose.pt",
    "obb": "-obb.pt",
}


class TrainRequest(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    dataset_version_id: str
    task: TrainingTask
    model_path: str
    epochs: int = Field(default=100, ge=1, le=10000)
    imgsz: int = Field(default=640, ge=32, le=8192)
    batch: int = Field(default=-1, ge=-1)
    device: str = "0"
    workers: int = Field(default=4, ge=0, le=32)
    patience: int = Field(default=100, ge=0)
    optimizer: str = "auto"
    lr0: float = Field(default=0.01, gt=0)
    lrf: float = Field(default=0.01, gt=0)
    momentum: float = Field(default=0.937, ge=0, le=1)
    weight_decay: float = Field(default=0.0005, ge=0)
    warmup_epochs: float = Field(default=3.0, ge=0)
    cos_lr: bool = False
    close_mosaic: int = Field(default=10, ge=0)
    amp: bool = True
    cache: bool | str = False
    seed: int = 0
    deterministic: bool = True
    degrees: float = Field(default=0.0, ge=0, le=180)
    translate: float = Field(default=0.1, ge=0, le=1)
    scale: float = Field(default=0.5, ge=0)
    shear: float = Field(default=0.0, ge=0, le=180)
    perspective: float = Field(default=0.0, ge=0, le=0.001)
    flipud: float = Field(default=0.0, ge=0, le=1)
    fliplr: float = Field(default=0.5, ge=0, le=1)
    hsv_h: float = Field(default=0.015, ge=0, le=1)
    hsv_s: float = Field(default=0.7, ge=0, le=1)
    hsv_v: float = Field(default=0.4, ge=0, le=1)
    mosaic: float = Field(default=1.0, ge=0, le=1)
    mixup: float = Field(default=0.0, ge=0, le=1)
    copy_paste: float = Field(default=0.0, ge=0, le=1)
    augmentation_preset: AugmentationPreset = "none"
    resume: bool = False

    @model_validator(mode="after")
    def validate_model_task(self) -> "TrainRequest":
        name = PurePosixPath(self.model_path.replace("\\", "/")).name.lower()
        task_markers = ("-seg.pt", "-sem.pt", "-pose.pt", "-obb.pt")
        expected = TASK_MODEL_SUFFIX[self.task]
        valid = name.endswith(expected)
        if self.task == "detect":
            valid = name.endswith(".pt") and not name.endswith(task_markers)
        if not valid:
            raise ValueError("预训练模型类型与数据集任务不一致")
        if not self.model_path.replace("\\", "/").startswith("models/"):
            raise ValueError("模型必须位于项目 models 目录")
        return self
