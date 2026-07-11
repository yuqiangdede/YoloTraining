import argparse
import json
import math
import os
import traceback
from pathlib import Path
from uuid import uuid4


def shapes_from_result(result, task: str, root: Path, asset: dict) -> list[dict]:
    shapes: list[dict] = []
    names = result.names
    if task == "detect" and result.boxes is not None:
        for box, cls in zip(result.boxes.xyxyn.cpu().tolist(), result.boxes.cls.cpu().tolist()):
            shapes.append({"id": str(uuid4()), "labelId": str(names[int(cls)]), "kind": "rectangle", "points": [[box[0], box[1]], [box[2], box[3]]]})
    elif task == "segment" and result.masks is not None and result.boxes is not None:
        for polygon, cls in zip(result.masks.xyn, result.boxes.cls.cpu().tolist()):
            shapes.append({"id": str(uuid4()), "labelId": str(names[int(cls)]), "kind": "polygon", "points": polygon.tolist()})
    elif task == "pose" and result.keypoints is not None and result.boxes is not None:
        for points, confidence, cls in zip(result.keypoints.xyn.cpu().tolist(), result.keypoints.conf.cpu().tolist(), result.boxes.cls.cpu().tolist()):
            shapes.append({"id": str(uuid4()), "labelId": str(names[int(cls)]), "kind": "keypoints", "points": points, "visibility": [2 if value >= 0.5 else 1 if value > 0 else 0 for value in confidence]})
    elif task == "obb" and result.obb is not None:
        height, width = result.orig_shape
        for box, cls in zip(result.obb.xywhr.cpu().tolist(), result.obb.cls.cpu().tolist()):
            cx, cy, w, h, radians = box
            shapes.append({"id": str(uuid4()), "labelId": str(names[int(cls)]), "kind": "obb", "points": [[(cx-w/2)/width, (cy-h/2)/height], [(cx+w/2)/width, (cy+h/2)/height]], "rotation": math.degrees(radians)})
    elif task == "semantic" and getattr(result, "semantic_mask", None) is not None:
        from PIL import Image
        mask_dir = root / "uploads" / "masks" / "prelabels"
        mask_dir.mkdir(parents=True, exist_ok=True)
        mask_path = mask_dir / f"{asset['id']}.png"
        Image.fromarray(result.semantic_mask.data.cpu().numpy()).save(mask_path)
        shapes.append({"id": str(uuid4()), "labelId": "semantic", "kind": "mask", "points": [], "maskPath": mask_path.relative_to(root).as_posix()})
    return shapes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True); parser.add_argument("--request", required=True)
    args = parser.parse_args(); root = Path(args.root); request_path = Path(args.request)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(root / "resources"))
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        from ultralytics import YOLO
        model = YOLO(str(root / payload["modelPath"]))
        sources = [str(root / asset["path"]) for asset in payload["assets"]]
        results = model.predict(sources, conf=payload["confidence"], verbose=False)
        documents = []
        for asset, result in zip(payload["assets"], results):
            documents.append({
                "assetId": asset["id"], "task": payload["task"], "imageWidth": asset["width"],
                "imageHeight": asset["height"], "status": "DRAFT",
                "shapes": shapes_from_result(result, payload["task"], root, asset),
            })
        (request_path.parent / "result.json").write_text(json.dumps({"documents": documents}, ensure_ascii=False), encoding="utf-8")
        return 0
    except Exception as exc:
        (request_path.parent / "result.json").write_text(json.dumps({"error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
