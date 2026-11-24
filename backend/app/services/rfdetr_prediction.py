import base64
import io
from pathlib import Path

from PIL import ImageDraw, ImageFont


def predict(path: Path, source, confidence: float) -> tuple[list[dict], str]:
    from rfdetr import ClassThresholds, RFDETR

    model = RFDETR.from_checkpoint(path, device="cpu")
    detections = model.predict(source, threshold=ClassThresholds({}, default=confidence))
    names = detections.data.get("class_name", ())
    rows = []
    overlay = source.copy()
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    for i, (box, score, label) in enumerate(zip(detections.xyxy, detections.confidence, names), start=1):
        x1, y1, x2, y2 = map(float, box)
        points = [max(0.0, min(1.0, v)) for v in (x1 / source.width, y1 / source.height, x2 / source.width, y2 / source.height)]
        rows.append({"label": str(label), "confidence": round(float(score), 4), "kind": "rectangle", "points": points})
        draw.rectangle((x1, y1, x2, y2), outline="#00dd99", width=2)
        # 类别名完整保留在预测明细中，叠加图使用序号以适配系统字体。
        draw.text((x1 + 2, y1 + 2), str(i), fill="#00dd99", stroke_width=1, stroke_fill="black", font=font)
    output = io.BytesIO()
    overlay.save(output, format="JPEG", quality=90)
    return rows, "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
