"""Run one-epoch YOLO26 training smoke tests on project-local synthetic data."""

import argparse
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


LABELS = {
    "detect": "0 0.5 0.5 0.5 0.5",
    "segment": "0 0.25 0.25 0.75 0.25 0.75 0.75 0.25 0.75",
    "semantic": "0 0.25 0.25 0.75 0.25 0.75 0.75 0.25 0.75",
    "pose": "0 0.5 0.5 0.5 0.5 0.25 0.25 2 0.75 0.75 2",
    "obb": "0 0.25 0.25 0.75 0.25 0.75 0.75 0.25 0.75",
}
MODELS = {
    "detect": "yolo26n.pt", "segment": "yolo26n-seg.pt", "semantic": "yolo26n-sem.pt",
    "pose": "yolo26n-pose.pt", "obb": "yolo26n-obb.pt",
}


def build_dataset(root: Path, task: str) -> Path:
    dataset = root / "runs" / "smoke-validation" / "datasets" / task
    for split in ("train", "val"):
        (dataset / "images" / split).mkdir(parents=True, exist_ok=True)
        (dataset / "labels" / split).mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (64, 64), "white")
        ImageDraw.Draw(image).rectangle((16, 16, 48, 48), fill="orange")
        image.save(dataset / "images" / split / f"{split}.png")
        (dataset / "labels" / split / f"{split}.txt").write_text(LABELS[task], encoding="utf-8")
    yaml = f"path: {dataset.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: object\n"
    if task == "pose":
        yaml += "kpt_shape: [2, 3]\nflip_idx: [0, 1]\n"
    path = dataset / "data.yaml"
    path.write_text(yaml, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks", nargs="*", choices=MODELS, default=list(MODELS))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("YOLO_CONFIG_DIR", str(root / "resources"))
    os.chdir(root / "models" / "pretrained")
    from ultralytics import YOLO
    output = root / "runs" / "smoke-validation" / "training"
    if output.exists():
        shutil.rmtree(output)
    for task in args.tasks:
        print(f"SMOKE START {task}", flush=True)
        model = YOLO(str(root / "models" / "pretrained" / MODELS[task]))
        model.train(
            data=str(build_dataset(root, task)), epochs=1, imgsz=64, batch=1, workers=0,
            device=0, project=str(output), name=task, exist_ok=True, plots=False,
            save=False, val=False, cache=False, verbose=False, amp=False,
        )
        print(f"SMOKE PASS {task}", flush=True)


if __name__ == "__main__":
    main()
