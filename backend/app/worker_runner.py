import argparse
import json
import os
import traceback
from pathlib import Path


class PauseRequested(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--data", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    run_dir = root / "runs" / args.job
    os.environ.setdefault("YOLO_CONFIG_DIR", str(root / "resources"))
    raw_params = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    try:
        from ultralytics import YOLO
        from app.schemas.training import TrainRequest

        request = TrainRequest.model_validate(raw_params)
        params = request.model_dump()
        model_path = root / params.pop("model_path")
        params.pop("name", None)
        params.pop("dataset_version_id", None)
        params.pop("task", None)
        resume = bool(params.pop("resume", False))
        augmentation_preset = params.pop("augmentation_preset", "none")
        if augmentation_preset != "none":
            from app.services.augmentation_presets import build_augmentations

            params["augmentations"] = build_augmentations(augmentation_preset)
        last = next(iter(run_dir.rglob("last.pt")), None)
        model = YOLO(str(last if resume and last else model_path))
        if resume and last:
            params["resume"] = True

        def on_epoch_end(trainer) -> None:
            epoch = int(trainer.epoch) + 1
            total = int(params.get("epochs", 1))
            (run_dir / "progress.json").write_text(json.dumps({"epoch": epoch, "progress": round(epoch / total * 100)}), encoding="utf-8")
            control = run_dir / "control.json"
            if control.exists() and json.loads(control.read_text(encoding="utf-8")).get("action") in {"pause", "cancel"}:
                trainer.save_model()
                raise PauseRequested("safe checkpoint created")

        model.add_callback("on_train_epoch_end", on_epoch_end)
        model.train(data=args.data, project=str(run_dir), name="train", exist_ok=True, **params)
        (run_dir / "result.json").write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return 0
    except PauseRequested:
        action = json.loads((run_dir / "control.json").read_text(encoding="utf-8")).get("action")
        (run_dir / "result.json").write_text(json.dumps({"status": "paused" if action == "pause" else "cancelled"}), encoding="utf-8")
        return 2
    except Exception as exc:
        (run_dir / "result.json").write_text(json.dumps({"status": "failed", "error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
