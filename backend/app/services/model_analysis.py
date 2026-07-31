import json

from sqlalchemy import select

from app.models import AnalysisJob, Annotation, Asset, DatasetCategory
from app.services.state_machine import JobStatus


def shape_box(points: list[list[float]]) -> list[float] | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def box_iou(first: list[float], second: list[float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def evaluate_sample(ground_truth: list[dict], predictions: list[dict], iou_threshold: float) -> dict:
    candidates: list[tuple[float, int, int]] = []
    for prediction_index, prediction in enumerate(predictions):
        for truth_index, truth in enumerate(ground_truth):
            if prediction["label"] == truth["label"]:
                overlap = box_iou(prediction["box"], truth["box"])
                if overlap >= iou_threshold:
                    candidates.append((overlap, prediction_index, truth_index))
    matched_predictions: set[int] = set()
    matched_truth: set[int] = set()
    matches: list[dict] = []
    for overlap, prediction_index, truth_index in sorted(candidates, reverse=True):
        if prediction_index in matched_predictions or truth_index in matched_truth:
            continue
        matched_predictions.add(prediction_index)
        matched_truth.add(truth_index)
        matches.append({"predictionIndex": prediction_index, "groundTruthIndex": truth_index, "iou": round(overlap, 4)})
    return {
        "tp": len(matches), "fp": len(predictions) - len(matched_predictions), "fn": len(ground_truth) - len(matched_truth),
        "matches": matches,
    }


def run_analysis_job(root, session, job: AnalysisJob) -> None:
    from app.api.models import _get_cached_model

    assets = list(session.scalars(select(Asset).where(Asset.dataset_id == job.dataset_id, Asset.is_deleted.is_(False)).order_by(Asset.created_at)))
    annotations = {item.asset_id: item for item in session.scalars(
        select(Annotation).where(Annotation.asset_id.in_([asset.id for asset in assets]), Annotation.status.in_(["COMPLETED", "REVIEWED"]))
    )} if assets else {}
    assets = [asset for asset in assets if asset.id in annotations]
    if not assets:
        raise ValueError("数据集没有已完成标注的素材")
    categories = {item.id: item.name for item in session.scalars(select(DatasetCategory).where(DatasetCategory.dataset_id == job.dataset_id))}
    params = json.loads(job.params_json)
    model = _get_cached_model(root / job.model_path)
    samples: list[dict] = []
    totals = {"tp": 0, "fp": 0, "fn": 0}
    for index, asset in enumerate(assets):
        session.refresh(job)
        if job.status == JobStatus.CANCELLED:
            return
        document = json.loads(annotations[asset.id].document_json)
        truth = []
        for shape in document.get("shapes", []):
            box = shape_box(shape.get("points", []))
            label = categories.get(shape.get("labelId"))
            if box and label:
                truth.append({"label": label, "box": box})
        result = model.predict(str(root / asset.storage_path), conf=params["confidence"], verbose=False)[0]
        predictions = []
        if result.boxes is not None:
            names = result.names
            for box, confidence, class_id in zip(result.boxes.xyxyn.cpu().tolist(), result.boxes.conf.cpu().tolist(), result.boxes.cls.cpu().tolist()):
                label = str(names.get(int(class_id), int(class_id)) if isinstance(names, dict) else int(class_id))
                predictions.append({"label": label, "box": [float(value) for value in box], "confidence": round(float(confidence), 4)})
        evaluation = evaluate_sample(truth, predictions, params["iouThreshold"])
        for key in totals:
            totals[key] += evaluation[key]
        samples.append({
            "assetId": asset.id, "filename": asset.filename, "storagePath": asset.storage_path,
            "groundTruth": truth, "predictions": predictions, **evaluation,
        })
        job.progress = round((index + 1) * 100 / len(assets))
        session.commit()
    samples.sort(key=lambda sample: (sample["fp"] + sample["fn"], sample["fn"], sample["fp"]), reverse=True)
    job.result_json = json.dumps({"totals": totals, "sampleCount": len(samples), "samples": samples}, ensure_ascii=False)
    job.progress = 100
    job.status = JobStatus.SUCCEEDED
    session.commit()
