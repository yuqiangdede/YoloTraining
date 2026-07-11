import argparse
import json
import os
import shutil
import traceback
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    root, request_path = Path(args.root), Path(args.request)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(root / "resources"))
    output_dir = request_path.parent
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        from ultralytics import YOLO
        model = YOLO(str(root / payload.pop("modelPath")))
        payload.pop("format", None)
        output = Path(model.export(format="onnx", **payload))
        destination = output_dir / output.name
        if output.resolve() != destination.resolve():
            shutil.move(str(output), destination)
        relative = destination.relative_to(root).as_posix()
        (output_dir / "result.json").write_text(json.dumps({"status": "succeeded", "outputPath": relative}), encoding="utf-8")
        return 0
    except Exception as exc:
        (output_dir / "result.json").write_text(json.dumps({"status": "failed", "error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
