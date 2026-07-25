import csv
import math
from pathlib import Path
from typing import Iterable


TASK_METRIC_SUFFIX = {
    "detect": "B",
    "obb": "B",
    "segment": "M",
    "semantic": "M",
    "pose": "P",
}


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metric_key(rows: list[dict[str, object]], base: str, task: str) -> str | None:
    keys = [str(key).strip() for key in rows[0].keys()] if rows else []
    preferred = TASK_METRIC_SUFFIX.get(task)
    candidates = [f"{base}({preferred})"] if preferred else []
    candidates.extend([base, *sorted(key for key in keys if key.startswith(f"{base}(") and key not in candidates)])
    return next((candidate for candidate in candidates if candidate in keys), None)


def summarize_results(rows: Iterable[dict[str, object]], task: str, completed: bool = True) -> dict:
    rows = [{str(key).strip(): value for key, value in row.items()} for row in rows]
    if not completed:
        return {
            "state": "NOT_READY",
            "primaryMetric": None,
            "bestEpoch": None,
            "bestValue": None,
            "finalValue": None,
            "validationMetrics": {},
            "lossMetrics": {},
            "notes": ["TRAINING_NOT_COMPLETE"],
        }
    if not rows:
        return {
            "state": "INCOMPLETE",
            "primaryMetric": None,
            "bestEpoch": None,
            "bestValue": None,
            "finalValue": None,
            "validationMetrics": {},
            "lossMetrics": {},
            "notes": ["RESULTS_FILE_MISSING"],
        }

    primary_metric = _metric_key(rows, "metrics/mAP50-95", task) or _metric_key(rows, "metrics/mAP50", task)
    final = rows[-1]
    validation_metrics = {
        key: number
        for key, value in final.items()
        if key.startswith("metrics/") and (number := _number(value)) is not None
    }
    loss_metrics = {
        key: number
        for key, value in final.items()
        if (key.startswith("train/") or key.startswith("val/"))
        and key.endswith("_loss")
        and (number := _number(value)) is not None
    }
    if not primary_metric:
        return {
            "state": "INCOMPLETE",
            "primaryMetric": None,
            "bestEpoch": None,
            "bestValue": None,
            "finalValue": None,
            "validationMetrics": validation_metrics,
            "lossMetrics": loss_metrics,
            "notes": ["PRIMARY_VALIDATION_METRIC_MISSING"],
        }

    scored_rows = [(row, _number(row.get(primary_metric))) for row in rows]
    scored_rows = [(row, value) for row, value in scored_rows if value is not None]
    if not scored_rows:
        return {
            "state": "INCOMPLETE",
            "primaryMetric": primary_metric,
            "bestEpoch": None,
            "bestValue": None,
            "finalValue": None,
            "validationMetrics": validation_metrics,
            "lossMetrics": loss_metrics,
            "notes": ["PRIMARY_VALIDATION_METRIC_INVALID"],
        }

    best_row, best_value = max(scored_rows, key=lambda item: item[1])
    final_value = _number(final.get(primary_metric))
    epoch = _number(best_row.get("epoch"))
    return {
        "state": "SUFFICIENT",
        "primaryMetric": primary_metric,
        "bestEpoch": int(epoch) if epoch is not None else None,
        "bestValue": best_value,
        "finalValue": final_value,
        "validationMetrics": validation_metrics,
        "lossMetrics": loss_metrics,
        "notes": ["VALIDATION_METRICS_AVAILABLE"],
    }


def summarize_results_file(path: Path | None, task: str, completed: bool = True) -> dict:
    if path is None or not path.is_file():
        return summarize_results([], task, completed=completed)
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            return summarize_results(csv.DictReader(handle), task, completed=completed)
    except (OSError, csv.Error):
        return summarize_results([], task, completed=completed)
