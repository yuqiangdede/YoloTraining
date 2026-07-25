from typing import Literal

from app.schemas.common import ApiModel


class QualityIssue(ApiModel):
    code: str
    severity: Literal["BLOCKING", "WARNING", "INFO"]
    message: str
    asset_ids: list[str] = []
    details: dict = {}


class QualityReport(ApiModel):
    status: Literal["PASS", "WARNING", "BLOCKED"]
    generated_at: str
    asset_count: int
    annotated_count: int
    completed_count: int
    annotation_count: int
    class_counts: dict[str, int] = {}
    issues: list[QualityIssue] = []
