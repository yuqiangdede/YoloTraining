import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Annotation, Asset, Dataset, DatasetCategory
from app.schemas.annotations import AnnotationDocument
from app.schemas.quality import QualityIssue, QualityReport


def run_quality_check(session: Session, dataset: Dataset) -> dict:
    assets = list(session.scalars(select(Asset).where(Asset.dataset_id == dataset.id, Asset.is_deleted.is_(False))))
    annotations = list(session.scalars(select(Annotation).where(Annotation.asset_id.in_([item.id for item in assets])))) if assets else []
    by_asset = {item.asset_id: item for item in annotations}
    categories = list(session.scalars(select(DatasetCategory).where(DatasetCategory.dataset_id == dataset.id)))
    category_ids = {item.id for item in categories}
    category_names = {item.id: item.name for item in categories}
    issues: list[QualityIssue] = []
    class_counts: Counter[str] = Counter()
    duplicate_groups: dict[str, list[str]] = defaultdict(list)

    for asset in assets:
        duplicate_groups[asset.sha256].append(asset.id)
        annotation = by_asset.get(asset.id)
        if annotation is None:
            issues.append(QualityIssue(code="MISSING_ANNOTATION", severity="BLOCKING", message="Asset has no annotation", asset_ids=[asset.id]))
            continue
        if annotation.status not in {"COMPLETED", "REVIEWED"}:
            issues.append(QualityIssue(code="ANNOTATION_NOT_COMPLETED", severity="BLOCKING", message="Annotation is not completed", asset_ids=[asset.id], details={"status": annotation.status}))
        try:
            document = AnnotationDocument.model_validate(json.loads(annotation.document_json))
        except Exception as exc:
            issues.append(QualityIssue(code="INVALID_ANNOTATION", severity="BLOCKING", message="Annotation document is invalid", asset_ids=[asset.id], details={"error": str(exc)}))
            continue
        if document.task.value != dataset.task:
            issues.append(QualityIssue(code="TASK_MISMATCH", severity="BLOCKING", message="Annotation task does not match dataset task", asset_ids=[asset.id]))
        if not document.shapes:
            issues.append(QualityIssue(code="EMPTY_ANNOTATION", severity="WARNING", message="Annotation has no shapes", asset_ids=[asset.id]))
        for shape in document.shapes:
            if shape.label_id not in category_ids:
                issues.append(QualityIssue(code="UNKNOWN_CATEGORY", severity="BLOCKING", message="Annotation references an unknown category", asset_ids=[asset.id], details={"categoryId": shape.label_id}))
            else:
                class_counts[category_names[shape.label_id]] += 1

    for digest, asset_ids in duplicate_groups.items():
        if len(asset_ids) > 1:
            issues.append(QualityIssue(code="DUPLICATE_ASSET", severity="WARNING", message="Multiple assets have the same content hash", asset_ids=asset_ids, details={"sha256": digest}))
    unused = sorted(set(category_names.values()) - set(class_counts))
    if unused:
        issues.append(QualityIssue(code="UNUSED_CATEGORY", severity="WARNING", message="Some categories are not used", details={"categories": unused}))
    if len(class_counts) > 1:
        values = sorted(class_counts.values())
        if values[-1] >= values[0] * 20:
            issues.append(QualityIssue(code="CLASS_IMBALANCE", severity="WARNING", message="Class distribution is highly imbalanced", details={"classCounts": dict(class_counts)}))

    blocking = sum(issue.severity == "BLOCKING" for issue in issues)
    status = "BLOCKED" if blocking else "WARNING" if issues else "PASS"
    return QualityReport(
        status=status,
        generated_at=datetime.now(timezone.utc).isoformat(),
        asset_count=len(assets),
        annotated_count=len(by_asset),
        completed_count=sum(item.status in {"COMPLETED", "REVIEWED"} for item in annotations),
        annotation_count=sum(len(json.loads(item.document_json).get("shapes", [])) for item in annotations),
        class_counts=dict(class_counts),
        issues=issues,
    ).model_dump(mode="json", by_alias=True)
