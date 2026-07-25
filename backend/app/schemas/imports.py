from pydantic import Field, model_validator

from app.schemas.common import ApiModel


class VocImportRequest(ApiModel):
    source_path: str = Field(min_length=1, max_length=1000)
    name: str | None = Field(default=None, max_length=100)
    train_ratio: float = Field(default=0.8, gt=0, lt=1)
    val_ratio: float = Field(default=0.2, gt=0, lt=1)
    seed: int = 0

    @model_validator(mode="after")
    def ratios_total_one(self) -> "VocImportRequest":
        if abs(self.train_ratio + self.val_ratio - 1) > 1e-6:
            raise ValueError("训练集和验证集比例之和必须为 1")
        return self
