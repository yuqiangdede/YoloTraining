from pydantic import Field

from app.schemas.common import ApiModel


class AnalysisCreate(ApiModel):
    model_id: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.25, ge=0, le=1)
    iou_threshold: float = Field(default=0.5, gt=0, le=1)
